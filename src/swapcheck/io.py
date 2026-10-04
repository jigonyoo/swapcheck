"""Reading result files and evaluating the tiny row expressions swapcheck uses.

Rows are plain dicts. Nothing is dropped silently: a row that cannot be read,
a metric that is missing or not a finite number, raises ``InputError`` with
the file and line it came from.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["InputError", "Condition", "load_rows", "apply_where", "number"]


class InputError(ValueError):
    """A problem with the input files or options. Reported, never swallowed."""


# --- conditions: "col>0", "model=openai/gpt-4.1-mini", "success==true" -------

_COND = re.compile(r"^\s*([^<>=!]+?)\s*(<=|>=|!=|==|<|>|=)\s*(.*?)\s*$")


@dataclass(frozen=True)
class Condition:
    """``column OP value``. ``=`` and ``==`` are the same.

    If ``value`` parses as a number the comparison is numeric, otherwise it is
    a string comparison (``true``/``false`` match JSON booleans).
    """

    column: str
    op: str
    value: str
    text: str

    @classmethod
    def parse(cls, text: str) -> "Condition":
        m = _COND.match(text)
        if not m:
            raise InputError(f"cannot parse condition {text!r}; expected e.g. 'duplicate_effects>0'")
        col, op, val = m.group(1), m.group(2), m.group(3)
        if op == "=":
            op = "=="
        if val == "":
            raise InputError(f"condition {text!r} has no value")
        return cls(col, op, val, text.strip())

    def _target(self):
        low = self.value.lower()
        if low in ("true", "false"):
            return low == "true"
        try:
            return float(self.value)
        except ValueError:
            return self.value

    def test(self, row: dict, where: str = "") -> bool:
        if self.column not in row:
            raise InputError(f"{where}column {self.column!r} (from {self.text!r}) is not in the row")
        got = row[self.column]
        target = self._target()
        if isinstance(target, bool):
            if isinstance(got, str):
                got = got.strip().lower() in ("true", "1", "yes")
            return _cmp(bool(got), self.op, target, self)
        if isinstance(target, float):
            return _cmp(number(got, self.column, where), self.op, target, self)
        if self.op not in ("==", "!="):
            raise InputError(f"condition {self.text!r}: '<'/'>' need a number")
        return _cmp(str(got), self.op, target, self)


def _cmp(a, op, b, cond):
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if isinstance(a, bool) or isinstance(b, bool):
        raise InputError(f"condition {cond.text!r}: '<'/'>' need a number")
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def number(value, column: str, where: str = "") -> float:
    """A finite float, or InputError. ``True``/``False`` become 1/0."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if value is None or value == "":
        raise InputError(f"{where}column {column!r} is empty")
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise InputError(f"{where}column {column!r} is not a number: {value!r}") from None
    if not math.isfinite(x):
        raise InputError(f"{where}column {column!r} is not finite: {value!r}")
    return x


def apply_where(rows: list[dict], conds: list[Condition], label: str) -> list[dict]:
    out = []
    for r in rows:
        if all(c.test(r, f"{label} {r.get('_src', '')}: ") for c in conds):
            out.append(r)
    return out


# --- loaders --------------------------------------------------------------------

def load_rows(path: str | Path, fmt: str = "auto") -> list[dict]:
    """Load rows from JSONL, CSV, or a promptfoo ``-o results.json`` file."""
    p = Path(path)
    if not p.is_file():
        raise InputError(f"no such file: {p}")
    if fmt == "auto":
        fmt = _sniff(p)
    if fmt == "jsonl":
        return _load_jsonl(p)
    if fmt == "csv":
        return _load_csv(p)
    if fmt == "promptfoo":
        from .promptfoo import load_promptfoo
        return load_promptfoo(p)
    raise InputError(f"unknown format {fmt!r}")


def _sniff(p: Path) -> str:
    name = p.name.lower()
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".json"):
        with p.open(encoding="utf-8") as f:
            head = f.read(4096).lstrip()
        if head.startswith("{") and ('"results"' in head or '"evalId"' in head):
            return "promptfoo"
        return "jsonl"
    raise InputError(f"cannot tell the format of {p.name}; pass --format jsonl|csv|promptfoo")


def _load_jsonl(p: Path) -> list[dict]:
    rows = []
    with p.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise InputError(f"{p.name}:{i}: not valid JSON ({e.msg})") from None
            if not isinstance(obj, dict):
                raise InputError(f"{p.name}:{i}: each line must be a JSON object")
            obj["_src"] = f"{p.name}:{i}"
            rows.append(obj)
    if not rows:
        raise InputError(f"{p.name}: no rows")
    return rows


def _load_csv(p: Path) -> list[dict]:
    rows = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise InputError(f"{p.name}: no header row")
        for i, row in enumerate(reader, 2):
            if None in row:
                raise InputError(f"{p.name}:{i}: more fields than the header")
            row = dict(row)
            row["_src"] = f"{p.name}:{i}"
            rows.append(row)
    if not rows:
        raise InputError(f"{p.name}: no rows")
    return rows
