# Track and enforce test coverage (#41)

## Context

`gulk-lib` has a healthy test suite (4 test files, ~1650 lines against 467 lines of source), but
there is **zero coverage tooling** in the repo: no `pytest-cov`, no `coverage`, no `.coveragerc`,
no `[tool.coverage.*]` section, and no coverage step in CI. Nothing stops a PR from adding
untested logic.

Today several modules have no direct tests at all — `game_config.validate_config()`,
`shuffle_deck.shuffle_deck()`, `build_deck.build_deck()`'s documented id-stability invariant,
and the `game_rounds.GAME_ROUNDS` table. Some are covered incidentally by the integration tests,
but nobody knows which, because coverage is never measured.

Goal: measure coverage on every CI run, surface it in the job log, and fail the build when it
drops below a floor — a ratchet that can only be raised deliberately.

## Approach

Add `pytest-cov` and drive enforcement from a new `make coverage` target that CI runs in place of
`make test`. Keep `make test` as the fast, un-instrumented inner dev loop.

### 1. Dependency — `packages/gulk-lib/pyproject.toml`

Add `pytest-cov>=7.0.0` to `[dependency-groups] dev`, then run `uv lock` from the workspace root
to regenerate `uv.lock` (CI uses `uv sync --locked` and will fail on a stale lock).

`pypi.org` and `files.pythonhosted.org` are already on the `.github/egress-firewall.yaml`
allowlist, so no firewall change is needed.

### 2. Coverage config — `packages/gulk-lib/pyproject.toml`

Add alongside the existing `[tool.pytest.ini_options]`:

```toml
[tool.coverage.run]
source_pkgs = ["gulk_lib"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = true
exclude_also = [
  "if TYPE_CHECKING:",
  "raise NotImplementedError",
  "^\\s*\\.\\.\\.$",
]
```

`source_pkgs` (not `source`) is the right knob for the src layout: coverage resolves the package
by import name via the editable install that `uv sync` creates, so it works from any working
directory and is unaffected by `--import-mode=importlib`.

Deliberately **not** adding `--cov` to `addopts`: that would instrument every bare `pytest` run
and slow the snapshot/watch loop.

Deliberately **not** setting `fail_under` in config: the threshold belongs on the CLI so that a
developer running `uv run pytest tests/test_scoring.py` doesn't get a spurious failure.

### 3. Makefile — `packages/gulk-lib/Makefile`

Leave `test`, `check`, `update-snapshots`, `watch` as-is. Add:

```make
coverage:
	uv run pytest --cov --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)
```

with `COVERAGE_MIN = <baseline>` defined at the top of the file (single place to ratchet), and
`coverage` added to `.PHONY`.

### 4. CI — `.github/workflows/ci.yml`

Replace the `- run: make test` step (line 50) with `- run: make coverage`. Running both would
execute the suite twice for no benefit; `make coverage` runs the same tests plus the threshold.

Optionally append the terminal report to `$GITHUB_STEP_SUMMARY` so the number is visible without
opening the log.

### 5. Set the floor (do this *after* steps 1–4 land locally)

1. Run `uv run pytest --cov --cov-report=term-missing` with no threshold to get the baseline.
2. Close the cheap gaps the report surfaces — these are low-effort, high-value:
   - `tests/test_game_config.py` — `validate_config()` accept/reject cases.
   - `tests/test_shuffle_deck.py` — `shuffle_deck()` with a seeded `random.Random`, asserting
     determinism and that the multiset of cards is preserved. The injectable `rng` parameter is
     already designed for this.
   - `tests/test_build_deck.py` — assert the documented invariant that jokers are appended last
     so card ids don't shift when joker count changes.
   New tests should follow the existing style in `tests/test_scoring.py` and reuse the builders
   in `tests/factories.py` (`make_player`, `make_deal`, `make_bid`, `make_play_card`).
3. Mark genuinely unreachable code rather than writing fake tests for it: add `# pragma: no cover`
   to the dead `hello()` stub in `src/gulk_lib/__init__.py` (or delete it — it has no callers).
4. Set `COVERAGE_MIN` to the achieved number, rounded **down** to a whole percent. Target 95%+;
   do not chase 100% at the cost of brittle assertions over the 20-row `GAME_ROUNDS` table.

### 6. Document — `packages/gulk-lib/CLAUDE.md`

Add `make coverage` to the Commands list, with a one-line note that CI enforces `COVERAGE_MIN`
and that raising it is the intended way to ratchet.

## Out of scope

`scripts/random_game.py` (232 lines) sits outside the package and outside the lint, typecheck, and
test perimeters entirely. Pulling it in is a separate concern — the active plan
`docs/plans/2026-11-19-gulk-lib-legal-actions.md` already proposes reworking it. Leave it out of
`source_pkgs` so it doesn't drag the number down.

No Codecov / external coverage service: it would require a new egress-firewall entry and a token,
and a local threshold already satisfies "track and enforce".

## Verification

From `packages/gulk-lib`:

1. `uv sync --locked` — succeeds, proving `uv.lock` was regenerated.
2. `make test` — still passes and is still fast (no coverage instrumentation).
3. `make coverage` — passes, prints a per-file `term-missing` table, and exits 0.
4. `make check` — `ruff check` (select = `ALL`), `pyright` strict, and `pyrefly` strict all pass on
   the new test files. Note `ANN201`/`ANN202` are ignored so test functions need no return
   annotation, but `ANN001` is active, so **fixture/helper parameters must be annotated**.
5. Ratchet sanity check: temporarily bump `COVERAGE_MIN` above the real number and confirm
   `make coverage` fails with a non-zero exit; revert.
6. Regression sanity check: temporarily add an untested branch to a `src/gulk_lib` module and
   confirm it shows up in the `Missing` column; revert.
7. Confirm the `ci` workflow still lints clean under `actionlint` (run `actionlint` from the
   workspace root), then push and confirm the `check` job runs `make coverage` and reports the
   percentage.
