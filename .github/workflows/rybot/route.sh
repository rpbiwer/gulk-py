#!/usr/bin/env bash
# Decides whether and how rybot responds to the event that triggered the
# workflow.
#
# Executed by the workflow: reads event fields from the environment and writes
# `skip`, `mode` and `ref` to $GITHUB_OUTPUT. Sourced by test-route.sh, which
# only uses the pure functions.
set -euo pipefail

# What may come before a mention: anything that can't be part of an email
# address or path, so `bot@rybot73.com` and `x/@rybot73` don't count.
PRE='(^|[^A-Za-z0-9_.@/-])'
# What may come after a mention or verb: optional sentence punctuation, then
# whitespace or the end of the line, so `@rybot73000`, `@rybot73-x` and
# `@rybot73.com` don't count.
POST='[,.!?:;)]*([[:space:]]|$)'
VERBS=(plan implement revise)

# has_mention <text>
has_mention() {
	grep -Eiq "${PRE}@rybot73${POST}" <<<"$1"
}

# matched_verbs <text>
# Prints each verb that directly follows a mention, one per line.
matched_verbs() {
	local verb
	for verb in "${VERBS[@]}"; do
		if grep -Eiq "${PRE}@rybot73[,:]?[[:space:]]*${verb}${POST}" <<<"$1"; then
			echo "$verb"
		fi
	done
}

# select_mode <event name> <is_pr> <text> <pr author>
# Prints the mode to run in, or `skip` if rybot shouldn't respond.
select_mode() {
	local event=$1 is_pr=$2 text=$3 pr_author=$4

	if [ "$event" = pull_request_review ]; then
		# Reviews on rybot's own PRs need no mention.
		if [ "$pr_author" = rybot73 ] || has_mention "$text"; then
			echo revise
		else
			echo skip
		fi
		return
	fi

	if ! has_mention "$text"; then
		echo skip
		return
	fi

	local verbs
	verbs=$(matched_verbs "$text" | paste -sd, -)
	if [ "$is_pr" = true ]; then
		case "$verbs" in
		revise) echo revise ;;
		*) echo answer ;;
		esac
	else
		case "$verbs" in
		plan) echo plan ;;
		implement) echo implement ;;
		*) echo answer ;;
		esac
	fi
}

# Environment: EVENT_NAME, IS_PR, TRIGGER_BODY, PR_AUTHOR,
# ISSUE_OR_PR_NUMBER, DEFAULT_BRANCH, GITHUB_REPOSITORY, GITHUB_OUTPUT,
# GH_TOKEN.
# shellcheck disable=SC2153 # set by the workflow
main() {
	local mode ref head cross
	mode=$(select_mode "$EVENT_NAME" "$IS_PR" "$TRIGGER_BODY" "$PR_AUTHOR")
	if [ "$mode" = skip ]; then
		echo "No exact @rybot73 mention; skipping."
		echo "skip=true" >>"$GITHUB_OUTPUT"
		return
	fi

	ref=$DEFAULT_BRANCH
	if [ "$IS_PR" = true ]; then
		read -r head cross < <(gh pr view "$ISSUE_OR_PR_NUMBER" --repo "$GITHUB_REPOSITORY" \
			--json headRefName,isCrossRepository --jq '"\(.headRefName) \(.isCrossRepository)"')
		if [ "$cross" = true ]; then
			gh pr comment "$ISSUE_OR_PR_NUMBER" --repo "$GITHUB_REPOSITORY" \
				--body "rybot doesn't work on pull requests from forks."
			echo "skip=true" >>"$GITHUB_OUTPUT"
			return
		fi
		ref=$head
	fi

	echo "Mode: $mode, ref: $ref"
	{
		echo "skip=false"
		echo "mode=$mode"
		echo "ref=$ref"
	} >>"$GITHUB_OUTPUT"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	main
fi
