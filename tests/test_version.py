"""The version lives in two places; fail if they drift apart."""

import re
import sys
from pathlib import Path

import swapcheck

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def project_version(text):
    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib.loads(text)["project"]["version"]
    # 3.10 has no tomllib: find `version = "..."` inside the [project] table
    in_project = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_project = line == "[project]"
        elif in_project:
            m = re.match(r'version\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    raise AssertionError("no version in [project] of pyproject.toml")


def test_pyproject_version_matches_package():
    assert project_version(PYPROJECT.read_text(encoding="utf-8")) == swapcheck.__version__
