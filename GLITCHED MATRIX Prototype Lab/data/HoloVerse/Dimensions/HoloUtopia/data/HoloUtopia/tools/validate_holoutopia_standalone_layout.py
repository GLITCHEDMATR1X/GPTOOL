"""Validate the standalone HoloUtopia package layout."""
from __future__ import annotations

from pathlib import Path
import sys


def main() -> int:
    here = Path(__file__).resolve()
    package_root = here.parents[3]
    checks = {
        "root main.py": package_root / "main.py",
        "windows launcher": package_root / "run_HoloUtopia.bat",
        "module root": package_root / "data" / "HoloUtopia",
        "database root": package_root / "data" / "database" / "utopia",
        "city atlas": package_root / "data" / "database" / "utopia" / "city_grid_atlas.json",
        "runtime bridge": package_root / "data" / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json",
        "runtime module": package_root / "data" / "HoloUtopia" / "holoutopia_game_runtime.py",
    }
    missing = [label for label, path in checks.items() if not path.exists()]
    bad = []
    if (package_root / "data" / "HoloVerse").exists():
        bad.append("data/HoloVerse should not exist in the standalone HoloUtopia package")
    duplicate_roots = [p.name for p in package_root.glob("holoutopia_*.py")]
    if duplicate_roots:
        bad.append("root-level duplicate holoutopia_*.py modules found: " + ", ".join(sorted(duplicate_roots)))
    if missing or bad:
        print("[holoutopia] FAIL standalone layout")
        for label in missing:
            print(f"  - missing {label}: {checks[label]}")
        for item in bad:
            print(f"  - {item}")
        return 2
    print("[holoutopia] OK standalone layout")
    print(f"  package_root={package_root}")
    print("  entry=main.py")
    print("  modules=data/HoloUtopia")
    print("  database=data/database/utopia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
