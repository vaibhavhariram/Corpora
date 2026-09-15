.PHONY: invariants test typecheck lint check

# The deterministic gate. Runs first in CI; the reviewer agent runs only if this passes.
# Cheap gate first, expensive judgment second.
invariants:
	@python3 scripts/check_invariants.py

test:
	@.venv/bin/pytest

typecheck:
	@.venv/bin/mypy

lint:
	@.venv/bin/ruff check src tests scripts

# Everything a PR must satisfy.
check: invariants test typecheck
