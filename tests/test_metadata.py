"""Validate publishing metadata with the standard-library TOML parser."""

from pathlib import Path

import pytest

import swapcheck

tomllib = pytest.importorskip("tomllib", reason="stdlib tomllib requires Python 3.11+")
ROOT = Path(__file__).resolve().parent.parent


def test_publishing_metadata():
    with (ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    assert project["name"] == "swapcheck"
    assert project["version"] == swapcheck.__version__ == "0.2.0"
    assert project["description"].strip()
    assert project["readme"] == {"file": "README.md", "content-type": "text/markdown"}
    assert (ROOT / project["readme"]["file"]).is_file()
    assert project["license"] == "MIT"
    assert project["requires-python"] == ">=3.10"
    assert project["keywords"] and all(k.strip() for k in project["keywords"])
    assert "Programming Language :: Python :: 3" in project["classifiers"]
    assert "Intended Audience :: Developers" in project["classifiers"]
    assert project["urls"] == {
        "Homepage": "https://jigonyoo.com",
        "Source": "https://github.com/jigonyoo/swapcheck",
        "Issues": "https://github.com/jigonyoo/swapcheck/issues",
    }
