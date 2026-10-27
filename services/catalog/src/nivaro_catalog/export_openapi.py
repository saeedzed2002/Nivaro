"""Export a stable contract without starting a database connection.

Use the frozen project environment for the canonical output. Offline fallback
tools may export to work/ for review, but must not establish release provenance.
"""

import argparse
import json
from pathlib import Path

from nivaro_catalog.main import app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    exported = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.check:
        if not args.path.exists() or args.path.read_text(encoding="utf-8") != exported:
            raise SystemExit("Catalog OpenAPI is stale; regenerate the canonical contract")
    else:
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(exported, encoding="utf-8")


if __name__ == "__main__":
    main()
