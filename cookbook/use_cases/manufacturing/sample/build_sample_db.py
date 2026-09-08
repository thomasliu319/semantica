"""Build the machine-shop SQLite sample database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Optional, Union

SAMPLE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = SAMPLE_DIR / "machine_shop.sqlite"


def build_sample_db(
    db_path: Optional[Union[str, Path]] = None,
    include_violations: bool = False,
) -> Path:
    """Create a fresh SQLite shop database from schema + seed SQL."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    try:
        conn.executescript((SAMPLE_DIR / "schema.sql").read_text(encoding="utf-8"))
        conn.executescript((SAMPLE_DIR / "seed.sql").read_text(encoding="utf-8"))
        if include_violations:
            conn.executescript(
                (SAMPLE_DIR / "seed_violations.sql").read_text(encoding="utf-8")
            )
        conn.commit()
    finally:
        conn.close()
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the machine-shop sample SQLite database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--violations", action="store_true")
    args = parser.parse_args()
    path = build_sample_db(args.db, include_violations=args.violations)
    print(path)


if __name__ == "__main__":
    main()
