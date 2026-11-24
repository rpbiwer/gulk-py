# CLAUDE.md

## Overview

Gulk is a trick-taking/bidding card game. This is a uv workspace (`packages/*`, Python >=3.12). Currently the only package is `packages/gulk-lib`, a pure, dependency-free game engine.

## Architecture

* Packages
  * gulk-lib
    * Pure game engine logic
* CI
  * `.github/workflows/rybot.yml` and `.github/workflows/rybot/`
    * Implements "rybot73", an unattended agent that plans/implements/revises on issues and PRs when a trusted user @-mentions it. Prompts are in `rybot/prompts/`, with operating rules in `rybot/system.md`.
