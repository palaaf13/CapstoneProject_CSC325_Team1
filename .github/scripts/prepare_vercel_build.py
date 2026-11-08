"""Write the files Vercel needs into the Deploy job's checkout, just before deploying.

None of this is committed. The repository stays free of host-specific config,
and the package pins Vercel installs are copied from requirements.txt at deploy
time, so the site always runs exactly the versions the Test stage ran.

Usage: python .github/scripts/prepare_vercel_build.py [repo_root]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PYTHON_VERSION = "3.13"
DEV_SECTION_MARKER = "# Dev / CI"
PIN = re.compile(r"^[A-Za-z0-9_.\-\[\]]+==[^\s#]+")

VERCEL_JSON = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "buildCommand": "npm ci && npm run tailwind:build",
    "functions": {"config/wsgi.py": {"maxDuration": 30}},
}

# Never upload local secrets, caches, or the test suite.
VERCELIGNORE = [
    ".env",
    ".env.*",
    ".git/",
    ".github/",
    ".venv/",
    "venv/",
    "node_modules/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    "staticfiles/",
    "tests/",
    "apps/*/tests/",
    ".vscode/",
    ".claude/",
]


def runtime_pins(requirements: str) -> list[str]:
    """Exact pins above the "# Dev / CI" line: what the site needs to run."""
    runtime, found, _ = requirements.partition(DEV_SECTION_MARKER)
    if not found:
        raise SystemExit(f"requirements.txt has no {DEV_SECTION_MARKER!r} line.")
    pins = []
    for raw in runtime.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not PIN.match(line):
            raise SystemExit(f"requirements.txt must pin exact versions, not {line!r}.")
        pins.append(line)
    if not pins:
        raise SystemExit("requirements.txt lists no runtime packages.")
    return pins


def project_table(pins: list[str]) -> str:
    """The [project] table Vercel's Python builder requires in pyproject.toml."""
    deps = "\n".join(f'    "{pin}",' for pin in pins)
    return (
        "[project]\n"
        'name = "ramhub"\n'
        'version = "0.0.0"\n'
        f'requires-python = ">={PYTHON_VERSION}"\n'
        f"dependencies = [\n{deps}\n]\n\n"
    )


def prepare(root: Path) -> None:
    pyproject = root / "pyproject.toml"
    current = pyproject.read_text()
    if re.search(r"^\[project\]", current, flags=re.MULTILINE):
        raise SystemExit("pyproject.toml already has a [project] table; refusing to guess.")

    pins = runtime_pins((root / "requirements.txt").read_text())
    pyproject.write_text(project_table(pins) + current)
    (root / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2) + "\n")
    (root / ".vercelignore").write_text("\n".join(VERCELIGNORE) + "\n")
    (root / ".python-version").write_text(PYTHON_VERSION + "\n")

    print(f"Prepared the Vercel build with {len(pins)} runtime packages:")
    for pin in pins:
        print(f"  {pin}")


if __name__ == "__main__":
    prepare(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
