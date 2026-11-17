#!/usr/bin/env bash
# Prints the Markdown context for an agent run: the issue or PR, its
# discussion, and the comment or review that triggered the run.
#
# Only text written by trusted users or rybot73 is included, so third-party
# text on this public repo never reaches the prompt.
#
# Environment: GH_TOKEN, GITHUB_REPOSITORY, ISSUE_OR_PR_NUMBER, IS_PR, MODE,
# TRUSTED_USERS (JSON array), TRIGGER_AUTHOR, TRIGGER_BODY.
set -euo pipefail

repo=$GITHUB_REPOSITORY
allowed=$(jq -c '. + ["rybot73"]' <<<"$TRUSTED_USERS")

# jq: keeps only elements written by an allowed author.
# shellcheck disable=SC2016 # jq variables, not shell ones
allowed_filter='map(select(.user.login as $u | $allowed | index($u)))'

item=$(gh api "repos/$repo/issues/$ISSUE_OR_PR_NUMBER")
author=$(jq -r '.user.login' <<<"$item")
kind=Issue
if [ "$IS_PR" = true ]; then
	kind="Pull request"
fi

echo "# Context"
echo
echo "- Repository: $repo"
echo "- Trusted users: $(jq -r 'join(", ")' <<<"$TRUSTED_USERS")"
echo "- $kind #$ISSUE_OR_PR_NUMBER, opened by @$author: $(jq -r '.html_url' <<<"$item")"
echo "- Labels: $(jq -r '[.labels[].name] | if length == 0 then "none" else join(", ") end' <<<"$item")"
if [ "$IS_PR" = true ]; then
	# shellcheck disable=SC2016 # backticks are Markdown
	gh api "repos/$repo/pulls/$ISSUE_OR_PR_NUMBER" --jq '"- Branch: `\(.head.ref)` → `\(.base.ref)`"'
fi
echo

if jq -e --arg u "$author" 'index($u) != null' <<<"$allowed" >/dev/null; then
	jq -r '"## Title\n\n\(.title)\n\n## Description\n\n\(.body // "_(empty)_")\n"' <<<"$item"
else
	echo "_The title and description were written by @$author, who isn't a trusted user, so they're omitted._"
	echo
fi

echo "## Comments"
echo
gh api --paginate "repos/$repo/issues/$ISSUE_OR_PR_NUMBER/comments" |
	jq -rs --argjson allowed "$allowed" "add // [] | $allowed_filter | .[] |
		\"### @\(.user.login), \(.created_at)\n\n\(.body)\n\""

if [ "$IS_PR" = true ]; then
	echo "## Reviews"
	echo
	gh api --paginate "repos/$repo/pulls/$ISSUE_OR_PR_NUMBER/reviews" |
		jq -rs --argjson allowed "$allowed" "add // [] | $allowed_filter |
			map(select((.body // \"\") != \"\")) | .[] |
			\"### @\(.user.login) (\(.state)), \(.submitted_at)\n\n\(.body)\n\""

	echo "## Unresolved review threads"
	echo
	# shellcheck disable=SC2016 # GraphQL variables, not shell ones
	gh api graphql -F owner="${repo%/*}" -F name="${repo#*/}" -F number="$ISSUE_OR_PR_NUMBER" -f query='
		query($owner: String!, $name: String!, $number: Int!) {
			repository(owner: $owner, name: $name) {
				pullRequest(number: $number) {
					reviewThreads(first: 100) {
						nodes {
							isResolved
							isOutdated
							path
							line
							originalLine
							comments(first: 100) {
								nodes { databaseId author { login } body diffHunk }
							}
						}
					}
				}
			}
		}' |
		jq -r --argjson allowed "$allowed" '
			.data.repository.pullRequest.reviewThreads.nodes[]
			| select(.isResolved | not)
			| .comments.nodes |= map(select(.author.login as $u | $allowed | index($u)))
			| select(.comments.nodes | length > 0)
			| "### `\(.path)`"
				+ (if (.line // .originalLine) then ":\(.line // .originalLine)" else "" end)
				+ (if .isOutdated then " (outdated)" else "" end)
				+ "\n\n```diff\n\(.comments.nodes[0].diffHunk)\n```\n\n"
				+ (.comments.nodes | map("- @\(.author.login) (comment ID \(.databaseId)): \(.body)") | join("\n"))
				+ "\n"'
fi

echo "## Trigger"
echo
echo "This run (mode: \`$MODE\`) was triggered by @$TRIGGER_AUTHOR:"
echo
if [ -n "$TRIGGER_BODY" ]; then
	printf '%s\n' "$TRIGGER_BODY"
else
	echo "_(A review with no summary; see its inline comments under the unresolved review threads.)_"
fi
