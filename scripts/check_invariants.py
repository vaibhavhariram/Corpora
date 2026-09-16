#!/usr/bin/env python3
"""Deterministic enforcement of the invariants in CLAUDE.md.

Why this exists as a script rather than a reviewer prompt
--------------------------------------------------------
Most of the invariants are mechanically checkable. Putting a language model on a
mechanically checkable constraint is the exact mistake this product exists to correct:
an LLM asked "does this add retrieval?" is right most of the time and silently wrong
occasionally, and occasional silent failure on invariant 1 ends the company. A grep is
right every time. ADR-0004 says a model may generate and may never judge; that applies
to our own tooling before it applies to anyone else's.

This runs in about two seconds, costs nothing, is never flaky, and needs no network. It
is the required check. The reviewer agent runs only after it passes, and only on the
residue that is genuinely judgment-shaped.

Deliberately NOT checked here
-----------------------------
Invariant 4 (transport errors are not retrieval misses) and invariant 5 (comparisons are
gated) are not greppable — they are behavioral properties of code that does not exist
yet. They belong in `tests/` once `run/` and `report/` are built. Their absence here is
a decision, not an oversight.

Usage:
    python scripts/check_invariants.py [--base <ref>]

`--base` is the ref to diff against for the change-sensitive checks (default: origin/main,
falling back to HEAD~1, then to skipping those checks with a warning).
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "corpora"
TESTS = ROOT / "tests"

# --------------------------------------------------------------------------- #
# Invariant 1 — Corpora never does retrieval
# --------------------------------------------------------------------------- #

# Importing any of these means the repo has started building a search engine. The list is
# deliberately broad: a false positive costs one conversation, a false negative costs the
# differentiator.
RETRIEVAL_PACKAGES = frozenset(
    {
        "faiss",
        "chromadb",
        "pinecone",
        "qdrant_client",
        "qdrant",
        "weaviate",
        "sentence_transformers",
        "haystack",
        "langchain",
        "langchain_core",
        "langchain_community",
        "llama_index",
        "elasticsearch",
        "opensearchpy",
        "annoy",
        "hnswlib",
        "usearch",
        "rank_bm25",
    }
)

# --------------------------------------------------------------------------- #
# Invariant 2 — No LLM in grading
# --------------------------------------------------------------------------- #

MODEL_AND_NETWORK_PACKAGES = frozenset(
    {
        "anthropic",
        "openai",
        "cohere",
        "google",
        "mistralai",
        "ollama",
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "http",
        "socket",
    }
)

# Only `generate/` may reach a model. Everything that decides a pass/fail, a score, a
# bucket, or a resolution must be provably unable to.
GRADING_PACKAGES = (
    "metrics", "run", "triage", "anchors", "diff", "report", "benchmark", "study",
)
MODEL_ALLOWED_PACKAGES = ("generate",)

VERIFIER_FILES = ("tests/test_anchors.py", "tests/fixtures/mutations.py")

# --------------------------------------------------------------------------- #
# Study firewall — a feasibility check must not be able to peek at the outcome
# --------------------------------------------------------------------------- #

FEASIBILITY_SCRIPT = "scripts/study_feasibility.py"
FEASIBILITY_FORBIDDEN = ("anchors", "diff")
"""Subpackages the pre-study feasibility check may not reach.

Confirming the design can detect an effect is legitimate; looking at the effect is not —
the same line a power analysis draws before a trial. Peeking would make the
pre-registration worthless, and a pre-registration is the only evidence of non-curation
that survives a sceptical reader.

Enforced here rather than in a docstring because "computed and then discarded" is not a
guarantee. The code path must not exist.
"""


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _import_roots(path: Path) -> set[str]:
    """Top-level package name of every import in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # a syntactically broken file is its own failure
        raise RuntimeError(f"{path.relative_to(ROOT)}: {exc}") from exc

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _local_imports(path: Path) -> set[str]:
    """Names of sibling `corpora` subpackages this module imports, relative or absolute."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0 and node.module:
                out.add(node.module.split(".")[0])
            elif node.module and node.module.startswith("corpora."):
                parts = node.module.split(".")
                if len(parts) > 1:
                    out.add(parts[1])
    return out


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #


def check_no_retrieval() -> list[str]:
    """Invariant 1. No index, no embeddings, no vector store, no ranking."""
    violations = []
    for path in _py_files(SRC):
        for hit in sorted(_import_roots(path) & RETRIEVAL_PACKAGES):
            violations.append(
                f"{path.relative_to(ROOT)} imports {hit!r} — invariant 1: Corpora never "
                f"does retrieval. We grade someone else's."
            )
    return violations


def check_no_llm_in_grading() -> list[str]:
    """Invariant 2. A model may generate. It may never influence a pass/fail."""
    violations = []
    for package in GRADING_PACKAGES:
        pkg_dir = SRC / package
        if not pkg_dir.exists():
            continue
        for path in _py_files(pkg_dir):
            for hit in sorted(_import_roots(path) & MODEL_AND_NETWORK_PACKAGES):
                violations.append(
                    f"{path.relative_to(ROOT)} imports {hit!r} — invariant 2: grading is "
                    f"deterministic. Only {'/'.join(MODEL_ALLOWED_PACKAGES)}/ may reach a model."
                )

    # Reachability: a grading package must not import a local package that itself can
    # reach a model. Catches laundering a model call through a helper module.
    tainted = set()
    for package in MODEL_ALLOWED_PACKAGES:
        if (SRC / package).exists():
            tainted.add(package)
    for package in GRADING_PACKAGES:
        pkg_dir = SRC / package
        if not pkg_dir.exists():
            continue
        for path in _py_files(pkg_dir):
            for local in sorted(_local_imports(path) & tainted):
                violations.append(
                    f"{path.relative_to(ROOT)} imports the {local!r} package — invariant 2: "
                    f"grading code must not be able to reach a model, even indirectly."
                )
    return violations


def check_dependency_allowlist() -> list[str]:
    """Invariant 1, early warning. A new dependency is the first sign of scope creep."""
    allowlist_path = ROOT / "scripts" / "allowed_deps.txt"
    if not allowlist_path.exists():
        return [f"missing {allowlist_path.relative_to(ROOT)}"]

    allowed = {
        line.split("#", 1)[0].strip().lower()
        for line in allowlist_path.read_text().splitlines()
        if line.split("#", 1)[0].strip()
    }

    with (ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)

    project = pyproject.get("project", {})
    declared: set[str] = set()
    for spec in project.get("dependencies", []):
        declared.add(_dep_name(spec))
    for extra in project.get("optional-dependencies", {}).values():
        for spec in extra:
            declared.add(_dep_name(spec))

    return [
        (
            f"dependency {name!r} is not in scripts/allowed_deps.txt — adding a "
            f"dependency is the earliest signal of scope creep. If it belongs, add it "
            f"to the allowlist in the same PR and say why in the description."
        )
        for name in sorted(declared - allowed)
    ]


def _dep_name(spec: str) -> str:
    name = spec.strip()
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        name = name.split(sep, 1)[0]
    return name.strip().lower()


def check_normalizer_versioned(base: str | None) -> list[str]:
    """Invariant 3. Changing the normalizer invalidates every anchor ever captured."""
    if base is None:
        return []
    changed = _changed_files(base)
    target = "src/corpora/corpus/normalize.py"
    if target not in changed:
        return []

    diff = _run(["git", "diff", _merge_base(base), "--unified=0", "--", target])
    touched_version = any(
        line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
        and "NORMALIZER_VERSION" in line
        for line in diff.splitlines()
    )
    if touched_version:
        return []

    # A comment-only edit changes no behavior, so demanding a version bump for one would
    # invalidate every anchor ever captured in exchange for nothing. Compare the parsed
    # tree rather than the diff: comments are absent from the AST, string literals and
    # docstrings are not, so anything that could alter normalization still trips this.
    previous = _run(["git", "show", f"{_merge_base(base)}:{target}"])
    if previous:
        try:
            before = _behavioral_ast(previous)
            after = _behavioral_ast((ROOT / target).read_text(encoding="utf-8"))
        except SyntaxError:
            before, after = "", "unparsed"
        if before == after:
            return []
    message = (
        f"{target} changed but NORMALIZER_VERSION did not — invariant 3. Changing the "
        f"normalizer silently invalidates every anchor captured under the old version. "
        f"Bump the version and write an ADR."
    )
    return [message]


class _StripStringStatements(ast.NodeTransformer):
    """Drops bare string expressions — docstrings and attribute docs."""

    def visit_Expr(self, node: ast.Expr) -> ast.Expr | None:
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return None
        return node


def _behavioral_ast(source: str) -> str:
    """Parsed form with comments and prose removed.

    Comments never reach the AST; bare string statements are stripped here. Neither can
    change what `normalize()` does, so neither should force a NORMALIZER_VERSION bump —
    a bump invalidates every anchor ever captured, which is far too high a price for
    rewording a docstring. Anything that could alter normalization (a dash mapping, a
    regex pattern, a code path) survives this and still trips the check.
    """
    return ast.dump(_StripStringStatements().visit(ast.parse(source)))


def check_verifier_protected(base: str | None) -> list[str]:
    """Test discipline. The loop must not be able to edit its own scorer.

    An agent under pressure to make tests pass will eventually weaken a test. That is the
    most common agentic coding failure and it is reward hacking. The verifier files are
    the scorer; changing them requires a deliberate second action.
    """
    if base is None:
        return []
    changed = _changed_files(base)
    touched = [f for f in VERIFIER_FILES if f in changed]
    if not touched:
        return []

    labels = {label.strip() for label in os.environ.get("PR_LABELS", "").split(",")}
    body = os.environ.get("PR_BODY", "")
    has_label = "verifier-change" in labels
    has_adr = "docs/decisions/" in body

    if has_label and has_adr:
        return []

    missing = []
    if not has_label:
        missing.append("the 'verifier-change' label")
    if not has_adr:
        missing.append("a docs/decisions/NNNN- reference in the PR body")
    message = (
        f"{', '.join(touched)} changed without {' and '.join(missing)}. The mutation "
        f"table and the anchor spec are the scorer. Editing them to make code pass is "
        f"reward hacking; editing them deliberately needs an ADR arguing the change."
    )
    return [message]


def check_study_firewall() -> list[str]:
    """The feasibility check may not resolve anchors. See docs/study-protocol.md 8c."""
    script = ROOT / FEASIBILITY_SCRIPT
    if not script.exists():
        return []

    reached = set()
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if parts[0] == "corpora" and len(parts) > 1:
                reached.add(parts[1])

    hits = sorted(reached.intersection(FEASIBILITY_FORBIDDEN))
    return [
        (
            f"{FEASIBILITY_SCRIPT} imports corpora.{hit} — the pre-study feasibility check "
            f"may confirm the design can detect an effect, never look at the effect. "
            f"Resolving anchors before the run makes the pre-registration worthless. "
            f"See docs/study-protocol.md section 8c."
        )
        for hit in hits
    ]


def check_library_first() -> list[str]:
    """Invariant 6. If there is logic in cli.py, it is in the wrong file."""
    cli = SRC / "cli.py"
    if not cli.exists():
        return []

    forbidden = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ListComp, ast.DictComp)
    violations = []
    tree = ast.parse(cli.read_text(encoding="utf-8"), filename=str(cli))
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            violations.append(
                f"src/corpora/cli.py:{node.lineno} contains {type(node).__name__} — "
                f"invariant 6: cli.py is argument parsing and nothing else. Move the logic "
                f"into an importable function."
            )
    return violations


def check_no_orphan_modules() -> list[str]:
    """Scope creep. Code that no test imports is code nobody asked for."""
    imported: set[str] = set()
    for path in _py_files(TESTS):
        text = path.read_text(encoding="utf-8")
        for module in _module_names():
            if f"corpora.{module}" in text or f"import {module}" in text:
                imported.add(module)

    return [
        (
            f"src/corpora/{module.replace('.', '/')}.py is imported by no test — every "
            f"module needs a test behind it. If it is not worth testing, it is not "
            f"worth shipping."
        )
        for module in sorted(set(_module_names()) - imported)
    ]


def _module_names() -> Iterable[str]:
    for path in _py_files(SRC):
        if path.name == "__init__.py":
            continue
        yield ".".join(path.relative_to(SRC).with_suffix("").parts)


# --------------------------------------------------------------------------- #
# Git helpers
# --------------------------------------------------------------------------- #


def _run(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout


def _merge_base(base: str) -> str:
    out = _run(["git", "merge-base", base, "HEAD"]).strip()
    return out or base


def _changed_files(base: str) -> set[str]:
    """Files changed since the merge-base, INCLUDING uncommitted working-tree changes.

    Deliberately not `base...HEAD`, which sees only committed work. In CI the two are
    equivalent, but locally `make invariants` is most useful before you commit — a gate
    that goes quiet exactly when you are still editing is a gate you learn to ignore.
    """
    out = _run(["git", "diff", "--name-only", _merge_base(base)])
    return {line.strip() for line in out.splitlines() if line.strip()}


def _resolve_base(requested: str | None) -> str | None:
    candidates = [requested] if requested else ["origin/main", "HEAD~1"]
    for ref in candidates:
        if ref and subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=ROOT,
            capture_output=True,
            check=False,
        ).returncode == 0:
            return ref
    return None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=None, help="ref to diff against")
    args = parser.parse_args()

    base = _resolve_base(args.base)

    checks = [
        ("no_retrieval", check_no_retrieval()),
        ("no_llm_in_grading", check_no_llm_in_grading()),
        ("dependency_allowlist", check_dependency_allowlist()),
        ("normalizer_versioned", check_normalizer_versioned(base)),
        ("verifier_protected", check_verifier_protected(base)),
        ("study_firewall", check_study_firewall()),
        ("library_first", check_library_first()),
        ("no_orphan_modules", check_no_orphan_modules()),
    ]

    failed = 0
    for name, violations in checks:
        if violations:
            failed += 1
            print(f"FAIL  {name}")
            for v in violations:
                print(f"        {v}")
        else:
            skipped = base is None and name in {
                "normalizer_versioned",
                "verifier_protected",
            }
            print(f"{'SKIP' if skipped else 'ok  '}  {name}")

    if base is None:
        print("\nnote: no base ref found; change-sensitive checks were skipped.")

    if failed:
        print(f"\n{failed} invariant check(s) failed.")
        return 1
    print("\nall invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
