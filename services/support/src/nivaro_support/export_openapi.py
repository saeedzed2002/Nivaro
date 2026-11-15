import argparse
import json
from pathlib import Path

from nivaro_support.main import app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    exported = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.check:
        if not args.path.exists() or args.path.read_text(encoding="utf-8") != exported:
            raise SystemExit("Support OpenAPI is stale; regenerate the canonical contract")
    else:
        args.path.write_text(exported, encoding="utf-8")


if __name__ == "__main__":
    main()
