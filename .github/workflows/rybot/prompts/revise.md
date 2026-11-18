You're on the branch of pull request #{{NUMBER}}. Revise it based on the trusted users' feedback below.

1. Address every unresolved review thread in the context, plus the trigger comment or review.
2. If the pull request has the `plan` label, it contains only a plan document: edit the plan, and don't implement it.
3. Commit, then push to this same branch. Never force-push.
4. Reply briefly on each review thread you addressed: `gh api repos/{owner}/{repo}/pulls/{{NUMBER}}/comments/<comment ID>/replies -f body=...`.
5. Post a summary comment on #{{NUMBER}}.
