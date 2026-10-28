"""Prepare an isolated P04 dependency probe without editing either running service."""

import json
import tomllib
from pathlib import Path

root = Path("/repo")
destination = Path("/preparation")
dependencies: set[str] = set()
constraints: dict[str, str] = {}
for service in ("catalog", "identity"):
    directory = root / "services" / service
    project = tomllib.loads((directory / "pyproject.toml").read_text())
    lock = tomllib.loads((directory / "uv.lock").read_text())
    dependencies.update(project["project"]["dependencies"])
    dependencies.update(project["dependency-groups"]["dev"])
    dependencies.update(project["build-system"]["requires"])
    for package in lock["package"]:
        if "registry" not in package.get("source", {}):
            continue
        name, version = package["name"], package["version"]
        if name in constraints and constraints[name] != version:
            raise SystemExit(
                f"Existing service locks disagree on {name}; review before downloading."
            )
        constraints[name] = version

# Only new P04 libraries. Celery includes Kombu/AMQP; aio-pika is for later events.
dependencies.update(("celery==5.6.3", "Pillow==13.0.0", "python-multipart==0.0.32"))
destination.mkdir(parents=True, exist_ok=True)
source = (
    '[project]\nname = "nivaro-p04-dependency-probe"\nversion = "0.0.0"\n'
    'requires-python = ">=3.13,<3.14"\n'
    f"dependencies = {json.dumps(sorted(dependencies), indent=2)}\n\n"
    "[tool.uv]\npackage = false\n"
    f"constraint-dependencies = {json.dumps([f'{name}=={version}' for name, version in sorted(constraints.items())], indent=2)}\n"
)
(destination / "pyproject.toml").write_text(source)
# A previous success is not evidence for changed requirements or an interrupted run.
(destination / "ready.json").unlink(missing_ok=True)
print(
    "Prepared isolated P04 probe; existing service manifests, locks and environments are unchanged."
)
