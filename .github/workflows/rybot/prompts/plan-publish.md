A planning step just wrote a plan for issue #{{NUMBER}} and added it as one new, uncommitted file under `docs/plans/`. Publish it:

1. Find the new file, e.g. with `git status`.
2. On a new, appropriately named branch, commit only that file, then push the branch.
3. Open a pull request titled `[Plan] <short title>`, with the label `plan`. Its body should summarize the plan in a few lines and reference #{{NUMBER}} **without** a closing keyword: say "Plan for #{{NUMBER}}", not "Closes #{{NUMBER}}".
4. Comment on #{{NUMBER}} with the pull request's link and the plan's path.

Don't change anything else.
