#!/usr/bin/env bash
# Prints a prompt: the named template from prompts/, with placeholders filled
# in, followed by the run's context.
#
# Usage: build-prompt.sh <template name>
# Environment: ISSUE_OR_PR_NUMBER, RUNNER_TEMP (context is read from
# $RUNNER_TEMP/context.md).
set -euo pipefail

template="$(dirname "$0")/prompts/$1.md"
sed "s/{{NUMBER}}/$ISSUE_OR_PR_NUMBER/g" "$template"
printf '\n---\n\n'
cat "$RUNNER_TEMP/context.md"
