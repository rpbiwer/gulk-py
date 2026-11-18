# Plan: make an @rybot73 mention in an issue's opening description trigger a run (#21)

## Context

`.github/workflows/rybot.yml` only listens to `issue_comment` (created) and `pull_request_review` (submitted). Opening an issue fires an `issues` event (`opened`), which the workflow doesn't subscribe to. So `@rybot73` in the issue body (as in #20 and #21) never starts a run. The user has to add a separate comment. The goal is for a mention in the opening description to behave like the same text in a comment.

`route.sh` needs no logic change. `select_mode` already handles non-review events: no mention gives `skip`, and `plan`/`implement`/other give `plan`/`implement`/`answer` for an issue. `issues` events are never PRs, so `IS_PR` is `false`.

## Changes

### 1. `.github/workflows/rybot.yml`

- **`on:`** Add `issues: { types: [opened] }`.
- **Job `if`:** Add a third alternative next to the `issue_comment` and `pull_request_review` ones:
  ```yaml
  (github.event_name == 'issues' &&
    contains(github.event.issue.body, '@rybot73')) ||
  ```
  - The trusted-actor check already wraps all alternatives. On `opened`, the actor is the issue author.
  - No state check is needed, since a just-opened issue is open.
  - `route.sh` still does the exact matching.
- **`TRIGGER_BODY`:** In the Route and Gather context steps, change `github.event.comment.body || github.event.review.body` to `github.event.comment.body || github.event.review.body || github.event.issue.body`.
  - For `issue_comment`, `comment.body` is always non-empty, so it wins.
  - For a review with an empty body, `github.event.issue` is undefined, so the result is still empty.
- **Acknowledge step:** `COMMENT_ID` is empty for `issues` events. Add a third case, where the target is the issue itself:
  ```bash
  elif [ -n "$COMMENT_ID" ]; then target="issues/comments/$COMMENT_ID" ...
  else target="issues/$ISSUE_OR_PR_NUMBER" ...   # POST .../issues/N/reactions
  ```
  The "Remove acknowledgement" step already deletes `$TARGET/reactions/$REACTION_ID`, so it works unchanged. Keep the existing output names (`target`, `reaction_id`, `node_id`).
- `concurrency.group`, `ISSUE_OR_PR_NUMBER` and the egress guard already work for `issues` events through `github.event.issue.number`. Leave them alone.

### 2. `.github/workflows/rybot/gather-context.sh` (optional polish)

For an opening-description trigger, the issue body appears under "Description" and again under "Trigger". This is harmless, because the prompts say "trigger comment below" and the body is still the right text. If wanted, pass `EVENT_NAME` into the Gather context step. When it's `issues`, print "triggered by @X opening this issue; the trigger is the description above" instead of repeating the body. I'm skipping this by default to keep the diff small.

### 3. `.github/workflows/rybot/test-route.sh`

Add fixtures using `expect <mode> issues false ryb73 '<text>'`:
- `@rybot73 plan` gives `plan`
- `@rybot73 implement` gives `implement`
- `@rybot73 what is this?` gives `answer`
- `no mention` gives `skip`
- `bot@rybot73.com` gives `skip`
- A multi-line body with the mention on a later line gives the right mode

These document that the `issues` event shares the issue-comment routing. Run them with `bash .github/workflows/rybot/test-route.sh`.

## Caveats

- **rybot's PAT can't push workflow files.** The comment on the egress guard in `rybot.yml` says so. The `rybot.yml` edit therefore has to be applied by @ryb73, for example by committing it directly or opening the PR as himself. rybot can only deliver the `.github/workflows/rybot/*` changes (tests, optional gather-context tweak). If `implement` runs, expect rybot to report this and hand over the exact `rybot.yml` diff.
- `issues` events run the workflow from the default branch. The change only takes effect once merged to `main`. It won't affect #20 or #21 retroactively.
- Out of scope: `issues: edited`, which would re-run on every edit and cause duplicate runs. Also out of scope is a mention in a PR's opening body (`pull_request: opened`), which could be added the same way if wanted.

## Verification

1. `bash .github/workflows/rybot/test-route.sh` passes with the new fixtures.
2. `actionlint .github/workflows/rybot.yml` (if available) or a YAML parse shows the file is valid.
3. After merge to `main`, open a test issue as @ryb73 whose description contains `@rybot73 plan`.
   - Expect: 👀 on the issue, a plan PR opened, and the 👀 removed at the end.
4. Open an issue without a mention, or with `bot@rybot73.com`. Expect no run, or a run that skips at the Route step.
5. Re-check that comment-triggered runs on issues and PRs, and review-triggered runs, still acknowledge and run as before.
