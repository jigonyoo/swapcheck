"""Read a promptfoo results file (``promptfoo eval -o results.json``).

Each element of ``results.results`` becomes one row:

    case_id        testCase.description, else a hash of the test's vars; when two
                   different tests share a description, "description [vars:hash]"
    provider       provider.label, else provider.id
    prompt         prompt.label, else promptId
    success        1 if promptfoo marked the row as passing, else 0
    score          promptfoo's score for the row
    error          1 if the provider call failed (failureReason 2, ERROR), else 0.
                   promptfoo also fills its own "error" field with the reason an
                   assertion failed (failureReason 1, ASSERT); that is not an error.
                   Without a failureReason: 1 when there is an error and no grading.
    latency_ms     latencyMs
    cost           cost (0 when promptfoo did not record one)
    named:<name>   each entry of namedScores
    fail:<name>    number of failed assertions with that metric name
                   (assertion.metric, else assertion.type). A row that errored was
                   never graded; it counts as 1 for every assertion name in the file,
                   so a crash never reads as "no failures".

Why the case id is not ``testIdx``: with ``--repeat N`` promptfoo gives every
repeat of a test its own ``testIdx``, so grouping by it would treat three
repeats of one test as three independent cases and overstate certainty.
The vars it stores are the test's own (runtime ``__repeatIndex`` is removed),
so the same test gets the same id on every repeat.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .io import InputError

__all__ = ["load_promptfoo", "case_key"]


def _vars_hash(result: dict) -> str:
    tc = result.get("testCase") or {}
    vars_ = result.get("vars")
    if vars_ is None:
        vars_ = tc.get("vars", {})
    blob = json.dumps(vars_, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _description(result: dict) -> str | None:
    tc = result.get("testCase") or {}
    desc = tc.get("description") or result.get("description")
    return str(desc) if desc else None


def case_key(result: dict, ambiguous: frozenset = frozenset()) -> str:
    """The case id of one promptfoo result row.

    ``ambiguous`` holds descriptions that more than one distinct test uses;
    those get the vars hash appended so two tests are never merged into one case.
    """
    desc = _description(result)
    h = _vars_hash(result)
    if desc and desc not in ambiguous:
        return desc
    if desc:
        return f"{desc} [vars:{h}]"
    return "vars:" + h


def _failed_assertions(gr) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(gr, dict):
        return out
    comps = gr.get("componentResults") or []
    for c in comps:
        if not isinstance(c, dict):
            continue
        a = c.get("assertion") or {}
        name = a.get("metric") or a.get("type") or "assertion"
        if c.get("pass") is False:
            out[name] = out.get(name, 0) + 1
        else:
            out.setdefault(name, 0)
    return out


ERROR = 2   # promptfoo ResultFailureReason: NONE 0, ASSERT 1, ERROR 2


def _errored(r: dict) -> int:
    fr = r.get("failureReason")
    if fr is not None:
        return 1 if fr == ERROR else 0
    return 1 if (r.get("error") and not r.get("gradingResult")) else 0


def load_promptfoo(path: str | Path) -> list[dict]:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"{p.name}: not valid JSON ({e.msg})") from None
    summary = data.get("results") if isinstance(data, dict) else None
    results = summary.get("results") if isinstance(summary, dict) else None
    if not isinstance(results, list):
        raise InputError(f"{p.name}: expected a promptfoo output file with results.results[]")
    rows = []
    names: set[str] = set()
    fails: set[str] = set()
    parsed = []
    seen: dict[str, set[str]] = {}
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            raise InputError(f"{p.name}: results.results[{i}] is not an object")
        d = _description(r)
        if d:
            seen.setdefault(d, set()).add(_vars_hash(r))
        named = r.get("namedScores") or {}
        failed = _failed_assertions(r.get("gradingResult"))
        names.update(named)
        fails.update(failed)
        parsed.append((i, r, named, failed))
    ambiguous = frozenset(d for d, hs in seen.items() if len(hs) > 1)
    for i, r, named, failed in parsed:
        errored = _errored(r)
        prov = r.get("provider") or {}
        prompt = r.get("prompt") or {}
        if "score" not in r:
            raise InputError(f"{p.name}: results.results[{i}] has no score")
        row = {
            "case_id": case_key(r, ambiguous),
            "provider": prov.get("label") or prov.get("id") or "",
            "prompt": prompt.get("label") or r.get("promptId") or str(r.get("promptIdx", "")),
            "success": 1 if r.get("success") else 0,
            "score": r.get("score"),
            "error": errored,
            "latency_ms": r.get("latencyMs", 0) or 0,
            "cost": r.get("cost", 0) or 0,
            "_src": f"{p.name}:results[{i}]",
            "_format": "promptfoo",
        }
        for n in names:
            row[f"named:{n}"] = named.get(n)  # absent stays absent, never 0
        for n in fails:
            row[f"fail:{n}"] = 1 if errored else failed.get(n, 0)
        rows.append(row)
    if not rows:
        raise InputError(f"{p.name}: no results")
    return rows
