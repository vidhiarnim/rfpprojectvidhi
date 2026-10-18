"""Create the SQLite database and seed the sample evaluation criteria.

Usage:
    python db/seed.py            # create tables, seed criteria if the table is empty
    python db/seed.py --reset    # delete existing criteria and re-seed the defaults
    python db/seed.py --db path/to/other.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rfp_agent import database as db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="SQLite file path")
    parser.add_argument("--reset", action="store_true", help="re-seed default criteria")
    args = parser.parse_args()

    conn = db.connect(args.db)
    db.init_db(conn, seed=not args.reset)
    if args.reset:
        db.seed_criteria(conn, reset=True)
    print(f"Database ready: {args.db}")
    print(f"{'ID':<4}{'Criterion':<26}{'Weight':>8}{'Max':>6}  Active")
    for c in db.get_all_criteria(conn):
        print(f"{c['criterion_id']:<4}{c['name']:<26}{c['weight']:>7g}%{c['max_score']:>6g}  "
              f"{'yes' if c['is_active'] else 'no'}")
    total = sum(c["weight"] for c in db.get_active_criteria(conn))
    print(f"Active weight total: {total:g}%")


if __name__ == "__main__":
    main()
