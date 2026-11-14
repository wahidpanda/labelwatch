from pathlib import Path

import yaml

DEFAULT_SEED_FILE = Path(__file__).resolve().parents[3] / "config" / "seed_drugs.yaml"


def load_seed_drugs(path: Path = DEFAULT_SEED_FILE, *, start_with_only: bool = False) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    key = "start_with" if start_with_only else "seed_drugs"
    names = data.get(key) or []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError(f"{path}: '{key}' must be a list of ingredient names")
    seen: dict[str, None] = {}
    for name in names:
        seen.setdefault(name.strip().lower(), None)
    return list(seen)
