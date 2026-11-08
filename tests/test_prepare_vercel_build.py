"""The Deploy stage's Vercel setup installs exactly what the Test stage ran."""

import importlib.util
import json
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "scripts" / "prepare_vercel_build.py"

spec = importlib.util.spec_from_file_location("prepare_vercel_build", SCRIPT)
prepare_vercel_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_vercel_build)


@pytest.fixture
def checkout(tmp_path):
    """A copy of the files the script reads, so the real repo is never touched."""
    for name in ("pyproject.toml", "requirements.txt"):
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def requirement_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_vercel_gets_the_runtime_pins_and_no_dev_tools(checkout):
    prepare_vercel_build.prepare(checkout)

    project = tomllib.loads((checkout / "pyproject.toml").read_text())["project"]
    runtime, _, dev = (ROOT / "requirements.txt").read_text().partition("# Dev / CI")
    assert project["dependencies"] == requirement_lines(runtime)
    assert not set(project["dependencies"]) & set(requirement_lines(dev))


def test_existing_tool_config_survives(checkout):
    prepare_vercel_build.prepare(checkout)

    config = tomllib.loads((checkout / "pyproject.toml").read_text())
    assert config["tool"]["pytest"]["ini_options"]["DJANGO_SETTINGS_MODULE"]
    assert config["tool"]["ruff"]["line-length"] == 100


def test_vercel_serves_the_wsgi_app_and_builds_the_css(checkout):
    prepare_vercel_build.prepare(checkout)

    config = json.loads((checkout / "vercel.json").read_text())
    for entrypoint in config["functions"]:
        assert (ROOT / entrypoint).is_file(), entrypoint
    assert "tailwind:build" in config["buildCommand"]


def test_local_secrets_are_never_uploaded(checkout):
    prepare_vercel_build.prepare(checkout)

    ignored = (checkout / ".vercelignore").read_text().splitlines()
    assert {".env", ".env.*"} <= set(ignored)


def test_loose_pins_stop_the_deploy(checkout):
    (checkout / "requirements.txt").write_text("Django>=6\n# Dev / CI\npytest==9.1.1\n")

    with pytest.raises(SystemExit, match="exact versions"):
        prepare_vercel_build.prepare(checkout)


def test_it_refuses_to_run_twice(checkout):
    prepare_vercel_build.prepare(checkout)

    with pytest.raises(SystemExit, match="already has a"):
        prepare_vercel_build.prepare(checkout)
