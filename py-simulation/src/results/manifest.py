import json
import re
from datetime import datetime
from pathlib import Path


RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"


class SweepResultDir:
    def __init__(self, path: Path):
        self.path = path
        self.csv_path = path / "sweep_results.csv"
        self.state_path = path / "sweep_results.csv.state.json"
        self._state: dict | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_valid(self) -> bool:
        return self.csv_path.exists()

    @property
    def state(self) -> dict | None:
        if self._state is None and self.state_path.exists():
            with open(self.state_path) as f:
                self._state = json.load(f)
        return self._state

    @property
    def sweep_config_path(self) -> str | None:
        s = self.state
        return s.get("sweep_config") if s else None

    @property
    def started(self) -> datetime | None:
        s = self.state
        if s and "started" in s:
            return datetime.fromisoformat(s["started"])
        return None

    @property
    def n_completed(self) -> int:
        s = self.state
        return len(s["completed"]) if s and "completed" in s else 0

    @property
    def completed_hashes(self) -> set[str]:
        s = self.state
        if s and "completed" in s:
            return {c["hash"] for c in s["completed"] if "hash" in c}
        return set()

    @property
    def sweep_stem(self) -> str:
        m = re.search(r"^(.*)_\d{8}_\d{6}$", self.name)
        return m.group(1) if m else self.name

    @property
    def parsed_timestamp(self) -> datetime | None:
        m = re.search(r"_(\d{8}_\d{6})$", self.name)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            except ValueError:
                return None
        return None

    def __repr__(self) -> str:
        return f"<SweepResultDir {self.name!r} n={self.n_completed}>"


def scan_results(results_dir: str | Path | None = None) -> list[SweepResultDir]:
    root = Path(results_dir) if results_dir else RESULTS_DIR
    if not root.exists():
        return []

    dirs: list[SweepResultDir] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            sd = SweepResultDir(entry)
            if sd.is_valid:
                dirs.append(sd)
    return dirs
