"""Entry point: python -m digest_agent [--date YYYY-MM-DD] [--out FILE]"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import config, pipeline, sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="digest_agent", description="Build the executive delivery brief.")
    ap.add_argument("--date", help="run date, YYYY-MM-DD (default: today)")
    ap.add_argument("--data", type=Path, default=config.DATA_DIR, help="folder holding the Zoho exports")
    ap.add_argument("--out", type=Path, help="output HTML path")
    ap.add_argument("--quiet", action="store_true", help="suppress the console summary")
    args = ap.parse_args(argv)

    run_date = date.fromisoformat(args.date) if args.date else config.today()
    out_path = args.out or config.OUTPUT_DIR / f"exec_brief_{run_date:%Y-%m-%d}.html"

    try:
        res = pipeline.run(args.data, run_date, out_path)
    except sources.FeedNotFound as exc:
        print(f"error: could not identify the {exc} feed in {args.data}.\n"
              f"       Sheets are matched on column names -- check the export is complete.",
              file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Delivery Risk Brief — {run_date:%d %b %Y}")
        for fd in res.feeds:
            age = "undated" if fd.days_old is None else f"{fd.days_old}d old"
            print(f"  feed  {fd.name:<15} {fd.rows:>7,} rows  sheet={fd.sheet!r}  {age}")
        print(f"\n  {len(res.kpis)} KPIs, {len(res.actions)} actions, "
              f"{len(res.watch)} watch items, {len(res.caveats)} caveats")
        for a in res.actions:
            print(f"   {a.rank:02d} [{a.band:<7}] {a.title}")
            print(f"        {res.changes.get(a.id, '')}")
        print(f"\n  wrote {res.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
