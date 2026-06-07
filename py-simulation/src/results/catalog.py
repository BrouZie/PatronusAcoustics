import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .manifest import SweepResultDir, scan_results, RESULTS_DIR


class SweepCatalog:
    def __init__(self, results_dir: str | Path | None = None):
        self.results_dir = Path(results_dir) if results_dir else RESULTS_DIR
        self._dirs: list[SweepResultDir] | None = None

    def _ensure_scanned(self) -> list[SweepResultDir]:
        if self._dirs is None:
            self._dirs = scan_results(self.results_dir)
        return self._dirs

    def list_sweeps(self) -> list[SweepResultDir]:
        return list(self._ensure_scanned())

    def get(self, name: str) -> SweepResultDir | None:
        for d in self._ensure_scanned():
            if d.name == name:
                return d
        return None

    def filter_by_stem(self, stem: str) -> list[SweepResultDir]:
        return [d for d in self._ensure_scanned() if d.sweep_stem == stem]

    def filter_by_date(self, since: datetime, until: datetime | None = None) -> list[SweepResultDir]:
        result = []
        for d in self._ensure_scanned():
            ts = d.parsed_timestamp or d.started
            if ts is None:
                continue
            if ts >= since and (until is None or ts <= until):
                result.append(d)
        return result

    def load_csv(self, sweep_dir: SweepResultDir) -> list[dict[str, Any]]:
        if not sweep_dir.csv_path.exists():
            return []
        with open(sweep_dir.csv_path, newline="") as f:
            return list(csv.DictReader(f))

    def load_csv_as_dicts(self, sweep_dir: SweepResultDir) -> list[dict[str, Any]]:
        return self.load_csv(sweep_dir)

    def to_dataframe(self, sweep_dir: SweepResultDir):
        import pandas as pd
        return pd.read_csv(sweep_dir.csv_path)

    def latest(self, stem: str | None = None) -> SweepResultDir | None:
        candidates = self._ensure_scanned()
        if stem:
            candidates = [d for d in candidates if d.sweep_stem == stem]
        if not candidates:
            return None
        return max(candidates, key=lambda d: d.parsed_timestamp or d.started or datetime.min)
