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
    args = parser.parse_args()
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
