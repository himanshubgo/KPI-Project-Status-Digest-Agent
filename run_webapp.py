"""Start the Zoho - KPI/Status Digest Agent front end.

    python run_webapp.py [--port 5000] [--host 127.0.0.1] [--debug]

Then open the printed URL. Binds to localhost only unless --host is given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Import correctly no matter which directory this is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    # Arguments are parsed before the heavy import so --help stays instant.
    ap = argparse.ArgumentParser(description="Run the digest agent front end.")
    ap.add_argument("--host", default="127.0.0.1", help="interface to bind (default: localhost only)")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true", help="auto-reload on code changes")
    args = ap.parse_args()

    # Say something *before* importing the app. Pulling in pandas takes the
    # better part of a minute on a cold start, and a blank terminal for that
    # long is indistinguishable from a crash -- which is exactly how it gets
    # reported. flush=True because stdout is block-buffered when redirected.
    print("\n  Zoho - KPI/Status Digest Agent", flush=True)
    print("  Loading the agent (pandas import — up to a minute on first run)…", flush=True)

    from webapp.app import app

    print(f"  Ready. Open  ->  http://{args.host}:{args.port}", flush=True)
    print("  Ctrl+C to stop\n", flush=True)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
