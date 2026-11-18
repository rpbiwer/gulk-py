#!/usr/bin/env bash
# Fixture tests for route.sh's mention matching and mode selection.
# Usage: bash .github/workflows/rybot/test-route.sh
set -euo pipefail
# shellcheck source=SCRIPTDIR/route.sh
source "$(dirname "$0")/route.sh"

failures=0

# expect <expected mode> <event name> <is_pr> <pr author> <text>
expect() {
	local expected=$1 event=$2 is_pr=$3 pr_author=$4 text=$5 actual
	actual=$(select_mode "$event" "$is_pr" "$text" "$pr_author")
	if [ "$actual" != "$expected" ]; then
		printf 'FAIL: expected %s, got %s (%s, is_pr=%s, author=%s): %q\n' \
			"$expected" "$actual" "$event" "$is_pr" "$pr_author" "$text"
		failures=$((failures + 1))
	fi
}

issue() { expect "$1" issue_comment false ryb73 "$2"; }
pr_comment() { expect "$1" issue_comment true ryb73 "$2"; }

# Mentions
issue answer '@rybot73'
issue answer '@rybot73, please'
issue answer 'thanks @RYBOT73!'
issue answer '(cc @rybot73)'
issue answer '(@rybot73)'
issue answer 'what do you think @rybot73?'
issue answer $'first line\n@rybot73 what is this?'
issue skip '@rybot73000'
issue skip '@rybot73-x'
issue skip 'bot@rybot73.com'
issue skip '@rybot73.com'
issue skip 'x/@rybot73'
issue skip 'no mention here'

# Issue verbs
issue plan '@rybot73 plan'
issue plan '@RYBOT73 PLAN'
issue plan 'Hey @rybot73, plan this out.'
issue plan $'context\nso @rybot73 plan it please'
issue plan '@rybot73: plan'
issue implement '@rybot73 implement'
issue implement 'Hey @rybot73, implement this.'
issue implement '@rybot73 implement the plan'
issue answer '@rybot73 planning'
issue answer '@rybot73 plans'
issue answer '@rybot73 implementation?'
issue answer $'@rybot73\nplan'
issue answer '@rybot73 plan and @rybot73 implement'
issue answer '@rybot73 revise this'

# PR conversation comments
pr_comment revise '@rybot73 revise'
pr_comment revise '@rybot73: revise per the above'
pr_comment answer '@rybot73 why this approach?'
pr_comment answer '@rybot73 plan'
pr_comment answer '@rybot73 implement'
pr_comment answer '@rybot73 revise and @rybot73 plan'
pr_comment skip '@rybot73000 revise'

# Reviews
expect revise pull_request_review true rybot73 ''
expect revise pull_request_review true rybot73 'looks off, see inline'
expect revise pull_request_review true ryb73 '@rybot73 fix these'
expect skip pull_request_review true ryb73 'just notes'
expect skip pull_request_review true ryb73 'cc bot@rybot73.com'

# Issue opening descriptions route like issue comments
expect plan issues false ryb73 '@rybot73 plan'
expect implement issues false ryb73 '@rybot73 implement'
expect answer issues false ryb73 '@rybot73 what is this?'
expect skip issues false ryb73 'no mention'
expect skip issues false ryb73 'bot@rybot73.com'
expect plan issues false ryb73 $'Some details\nmore details\n@rybot73 plan'

if [ "$failures" -gt 0 ]; then
	echo "$failures failure(s)"
	exit 1
fi
echo "All route tests passed."
