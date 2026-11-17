# Plan: add `actionlint` and `shellcheck` to CI (issue #27)

## Context
`.github/workflows/ci.yml` has one job (`check`) that runs Python checks and the rybot route tests. Nothing lints the workflow YAML or the shell scripts. The scripts are `build-prompt.sh`, `gather-context.sh`, `route.sh` and `test-route.sh`, all in `.github/workflows/rybot/`. Both workflows (`ci.yml` and `rybot.yml`) also have inline `run:` blocks. `rybot.yml` has several multi-line ones. actionlint passes these to shellcheck when shellcheck is on PATH, so one actionlint run covers the inline blocks.

## Approach
Add a separate job `lint` to `ci.yml`. The existing `check` job sets `working-directory: packages/gulk-lib`, so a separate job avoids overriding it per step, and it runs in parallel with `check`.

```yaml
  lint:
    runs-on: ubuntu-24.04-firewall   # per .github/workflows/CLAUDE.md
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Install actionlint
        # download a pinned release; verify its sha256; extract to $RUNNER_TEMP
      - name: shellcheck
        run: git ls-files -z '*.sh' | xargs -0 shellcheck
      - name: actionlint
        run: actionlint   # also runs shellcheck on inline run: blocks
```

Details:
1. **shellcheck**: Ubuntu runner images normally ship it. The first CI run must confirm that `ubuntu-24.04-firewall` has it. If it doesn't, install the same way as actionlint, or via PyPI with `uvx --from shellcheck-py shellcheck` (pypi.org and files.pythonhosted.org are already allowed).
2. **actionlint**: Download the pinned release tarball from `github.com/rhysd/actionlint/releases`. Look up the latest version when implementing. Check the tarball against a hard-coded sha256 so the pin is as strong as the repo's SHA-pinning convention. `github.com` and `release-assets.githubusercontent.com` are already reachable under the egress firewall, so `.github/egress-firewall.yaml` needs no change. Fallback: `uvx --from actionlint-py actionlint`, which is PyPI-hosted but may fetch the binary at install time. Check it works under the firewall before relying on it.
3. **Scope**: use `git ls-files '*.sh'` so the `tools/claude-scripts` submodule is never linted. It isn't checked out in CI anyway.
4. **Dependabot**: the plain binary download won't be auto-bumped, so add a comment above the version and sha256 saying to update both together.

## Fix-ups likely needed
Lint has never run on these files. Run both tools locally first (if installable) or in the PR's CI, then fix real findings in the scripts and `rybot.yml`. Do not blanket-disable rules. Use targeted `# shellcheck disable=SCxxxx` with a reason only where a finding is a false positive. Add `.shellcheckrc` or `actionlint.yaml` only if needed.

## Critical files
- `.github/workflows/ci.yml` (new `lint` job)
- Possibly `.github/workflows/rybot.yml` and `.github/workflows/rybot/*.sh` (fixes for findings)

## Verification
- Run `shellcheck` and `actionlint` locally against the repo, or push the branch and check the new `lint` job.
- Confirm the `lint` job passes on the PR and that `check` is unaffected.
- Negative test: temporarily add an unquoted variable in a script and a bad `${{ }}` expression in a workflow. Confirm the job fails, then revert.
- Confirm the job isn't blocked by the egress firewall (download step succeeds).
