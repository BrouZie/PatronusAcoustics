import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.results import SweepResultDir, scan_results, SweepCatalog
from src.results.cache import has_cached, save_cache, load_cache, clear_cache, CACHE_DIR
from src.config import Config


def _make_sweep_dir(root: Path, name: str, n: int, stem: str):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)

    csv_path = d / "sweep_results.csv"
    with open(csv_path, "w") as f:
        f.write("param1,detection_rate,config_hash\n")
        for i in range(n):
            f.write(f"{i},{i / n:.2f},hash_{i:04x}\n")

    state = {
        "sweep_config": f"/config/sweep/{stem}.yaml",
        "started": datetime.now(timezone.utc).isoformat(),
        "output_path": str(csv_path.resolve()),
        "completed": [
            {"combo": [i], "hash": f"hash_{i:04x}", "status": "ok"}
            for i in range(n)
        ],
    }
    state_path = d / "sweep_results.csv.state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    return d


class TestSweepResultDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_name_and_stem(self):
        path = _make_sweep_dir(self.tmp, "test_sweep_20260101_120000", 3, "test_sweep")
        sd = SweepResultDir(path)
        self.assertEqual(sd.name, "test_sweep_20260101_120000")
        self.assertEqual(sd.sweep_stem, "test_sweep")

    def test_name_without_timestamp(self):
        d = self.tmp / "custom_run"
        d.mkdir()
        (d / "sweep_results.csv").touch()
        sd = SweepResultDir(d)
        self.assertEqual(sd.sweep_stem, "custom_run")

    def test_is_valid(self):
        path = _make_sweep_dir(self.tmp, "valid_20260101_120000", 1, "valid")
        sd = SweepResultDir(path)
        self.assertTrue(sd.is_valid)

    def test_is_valid_missing_csv(self):
        d = self.tmp / "no_csv"
        d.mkdir()
        sd = SweepResultDir(d)
        self.assertFalse(sd.is_valid)

    def test_n_completed(self):
        path = _make_sweep_dir(self.tmp, "test_20260101_120000", 5, "test")
        sd = SweepResultDir(path)
        self.assertEqual(sd.n_completed, 5)

    def test_completed_hashes(self):
        path = _make_sweep_dir(self.tmp, "test_20260101_120000", 3, "test")
        sd = SweepResultDir(path)
        self.assertEqual(sd.completed_hashes, {"hash_0000", "hash_0001", "hash_0002"})

    def test_sweep_config_path(self):
        path = _make_sweep_dir(self.tmp, "test_20260101_120000", 2, "my_sweep")
        sd = SweepResultDir(path)
        self.assertIn("/config/sweep/my_sweep.yaml", sd.sweep_config_path)

    def test_parsed_timestamp(self):
        path = _make_sweep_dir(self.tmp, "sweep_20260607_180718", 1, "sweep")
        sd = SweepResultDir(path)
        ts = sd.parsed_timestamp
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 6)
        self.assertEqual(ts.day, 7)

    def test_no_state_returns_defaults(self):
        d = self.tmp / "bare"
        d.mkdir()
        (d / "sweep_results.csv").touch()
        sd = SweepResultDir(d)
        self.assertIsNone(sd.state)
        self.assertIsNone(sd.started)
        self.assertEqual(sd.n_completed, 0)
        self.assertEqual(sd.completed_hashes, set())

    def test_repr(self):
        path = _make_sweep_dir(self.tmp, "rep_sweep_20260101_120000", 4, "rep")
        sd = SweepResultDir(path)
        r = repr(sd)
        self.assertIn("rep_sweep_20260101_120000", r)
        self.assertIn("n=4", r)


class TestScanResults(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sweeps = [
            ("alpha_20260101_100000", 3, "alpha"),
            ("beta_20260102_100000", 5, "beta"),
            ("gamma_20260103_100000", 2, "gamma"),
        ]
        for name, n, stem in self.sweeps:
            _make_sweep_dir(self.tmp, name, n, stem)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_discovers_all(self):
        dirs = scan_results(self.tmp)
        self.assertEqual(len(dirs), 3)

    def test_skips_dirs_without_csv(self):
        (self.tmp / "no_csv").mkdir()
        dirs = scan_results(self.tmp)
        self.assertEqual(len(dirs), 3)

    def test_sorted_by_name(self):
        dirs = scan_results(self.tmp)
        names = [d.name for d in dirs]
        self.assertEqual(names, sorted(names))

    def test_empty_dir_returns_empty(self):
        empty = Path(tempfile.mkdtemp())
        dirs = scan_results(empty)
        self.assertEqual(dirs, [])
        import shutil
        shutil.rmtree(empty)

    def test_results_dir_not_exists(self):
        dirs = scan_results("/nonexistent/path")
        self.assertEqual(dirs, [])


class TestSweepCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _make_sweep_dir(self.tmp, "range_20260101_100000", 3, "range")
        _make_sweep_dir(self.tmp, "range_20260102_100000", 5, "range")
        _make_sweep_dir(self.tmp, "height_20260101_100000", 2, "height")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_list_sweeps(self):
        cat = SweepCatalog(self.tmp)
        self.assertEqual(len(cat.list_sweeps()), 3)

    def test_get_by_name(self):
        cat = SweepCatalog(self.tmp)
        sd = cat.get("range_20260101_100000")
        self.assertIsNotNone(sd)
        self.assertEqual(sd.name, "range_20260101_100000")

    def test_get_nonexistent(self):
        cat = SweepCatalog(self.tmp)
        self.assertIsNone(cat.get("nope"))

    def test_filter_by_stem(self):
        cat = SweepCatalog(self.tmp)
        dirs = cat.filter_by_stem("range")
        self.assertEqual(len(dirs), 2)

    def test_filter_by_stem_none(self):
        cat = SweepCatalog(self.tmp)
        dirs = cat.filter_by_stem("band")
        self.assertEqual(dirs, [])

    def test_latest_without_stem(self):
        cat = SweepCatalog(self.tmp)
        latest = cat.latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.name, "range_20260102_100000")

    def test_latest_with_stem(self):
        cat = SweepCatalog(self.tmp)
        latest = cat.latest("range")
        self.assertEqual(latest.name, "range_20260102_100000")

    def test_latest_no_match(self):
        cat = SweepCatalog(self.tmp)
        self.assertIsNone(cat.latest("nope"))

    def test_load_csv(self):
        cat = SweepCatalog(self.tmp)
        sd = cat.get("height_20260101_100000")
        rows = cat.load_csv(sd)
        self.assertEqual(len(rows), 2)
        self.assertIn("param1", rows[0])
        self.assertIn("detection_rate", rows[0])

    def test_load_csv_missing_file(self):
        d = self.tmp / "no_csv"
        d.mkdir()
        sd = SweepResultDir(d)
        cat = SweepCatalog(self.tmp)
        self.assertEqual(cat.load_csv(sd), [])

    def test_to_dataframe(self):
        cat = SweepCatalog(self.tmp)
        sd = cat.get("height_20260101_100000")
        df = cat.to_dataframe(sd)
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(float(df["detection_rate"].sum()), 0.5)

    def test_caching(self):
        cat = SweepCatalog(self.tmp)
        first = cat._ensure_scanned()
        second = cat._ensure_scanned()
        self.assertIs(first, second)


def _fake_results():
    from src.metrics import MetricsResult
    return {
        "true_doas": np.array([[30.0, 10.0]]),
        "estimated_doas": np.array([[29.5, 9.8]]),
        "srp_maps": np.zeros((1, 5, 10)),
        "peak_values": np.array([0.8]),
        "detections": np.array([True]),
        "timestamps": np.array([0.0]),
        "frame_snrs": np.array([20.0]),
        "n_frames": 1,
        "fs": 48000,
        "metrics": MetricsResult(
            detection_rate=1.0,
            mean_angular_error_deg=0.5,
            std_angular_error_deg=0.1,
            max_angular_error_deg=0.5,
            mean_psr_db=10.0,
            mean_beamwidth_deg=20.0,
            n_detected=1,
            n_total=1,
        ),
    }


class TestSimulationCache(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_not_cached_initially(self):
        self.assertFalse(has_cached(Config()))

    def test_save_and_load_roundtrip(self):
        cfg = Config()
        results = _fake_results()
        save_cache(cfg, results)
        self.assertTrue(has_cached(cfg))

        loaded = load_cache(cfg)
        self.assertEqual(loaded["metrics"].detection_rate, 1.0)
        self.assertEqual(loaded["metrics"].mean_angular_error_deg, 0.5)
        self.assertEqual(loaded["n_frames"], 1)
        np.testing.assert_array_equal(loaded["true_doas"], [[30.0, 10.0]])
        np.testing.assert_array_equal(loaded["detections"], [True])

    def test_load_nonexistent_returns_none(self):
        self.assertIsNone(load_cache(Config()))

    def test_clear_specific(self):
        cfg = Config()
        save_cache(cfg, _fake_results())
        self.assertTrue(has_cached(cfg))
        n = clear_cache(cfg)
        self.assertEqual(n, 1)
        self.assertFalse(has_cached(cfg))

    def test_clear_all(self):
        save_cache(Config(), _fake_results())
        save_cache(Config(), _fake_results())
        n = clear_cache()
        self.assertGreaterEqual(n, 1)
        self.assertEqual(len(list(CACHE_DIR.iterdir())), 0)

    def test_cache_keyed_by_config(self):
        cfg1 = Config()
        cfg2 = Config.model_validate({**cfg1.model_dump(), "signal": {"duration": 99.0}})
        save_cache(cfg1, _fake_results())
        self.assertTrue(has_cached(cfg1))
        self.assertFalse(has_cached(cfg2))
