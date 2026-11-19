# Plan: gulk-lib legal-move queries (issue #2)

## Context

Part of the Godot front-end effort (`docs/plans/playable-ui.md`, step 1; parent #1). Legal-move
logic currently lives ad hoc in `scripts/random_game.py` (`legal_cards` at lines 53-73, and the
"screw the dealer" exclusion tangled into `_random_bid` and the bid loop at lines 129-145). The
future `gulk-server` bot loop and Godot UI both need it as a library API. This issue adds a new
`packages/gulk-lib/src/gulk_lib/legal_actions.py` as the single source of truth, plus tests.

Out of scope here (these are step 2 in the plan doc): wiring `get_legal_cards` into
`apply_event.py` (the line-68 follow-suit TODO) and switching `scripts/random_game.py` / the
integration test over to the new module. Leave both untouched so the golden-file integration
test is unaffected by the new functions.

## Key finding: dealer is not recorded in state

`get_next_actor` must know turn order, but `GameState`/`HandState` don't store who dealt.
`Deal.dealer_id` is consumed by nobody in `apply_event` (it's dropped; see
`apply_event.py:23`). Turn order in `random_game.py` and the integration test is:

- Bidding: starts with the player after the dealer, proceeds in seat order
  (`config.players` order), dealer bids last.
- Trick play: first trick led by the player after the dealer; each later trick led by the
  previous trick's winner (`finished_tricks[-1][0]`); within a trick, seat order from the leader.

**Decision (recommended): add `dealer_id: PlayerId | None = None` to `HandState`
(`game_state.py`), set from `Deal.dealer_id` in `apply_event`.** Rejected alternative:
inferring the dealer as `players[hand_index % n]`. It matches current usage but is a convention
of the fuzzer, not something the engine enforces, so it would silently break if dealer rotation
ever changes.

Cost of the recommendation: it changes `HandState`'s repr, so
- the 3 `Deal` snapshots in `tests/test_apply_event.py` (`test_deal_*`) and the golden file under
  `tests/integration/__inline_snapshot__/` change (regenerate; review the diff is *only* the
  added `dealer_id=...` field). This is a deviation from the plan doc's "golden file passes
  unchanged" note, which only covers step 2.
- Existing tests that hand-build `HandState(...)` keep working (default `None`).

If the maintainer prefers zero churn, fall back to the `hand_index % n` inference and drop the
`game_state.py` / `apply_event.py` changes; everything else in this plan is identical.

## Implementation

### 1. `game_state.py` / `apply_event.py` (small)
- `HandState`: add `dealer_id: PlayerId | None = None` with a docstring in the style of the
  other fields ("Player who dealt this hand; bidding and the first lead start with the next
  player in seat order").
- `apply_event` `Deal` case: pass `dealer_id=dealer_id` into `HandState(...)` (currently the
  pattern binds it as `_`).

### 2. New `legal_actions.py`
Follow repo style (plain functions, `assert` for invariant violations like `apply_event`).

- `get_legal_bids(state: GameState) -> list[int]`
  - Require `state.config` and `state.hand_state` (assert).
  - Return `[]` if everyone has already bid (not in bidding phase).
  - `cards_dealt = len(any player's hand)` (same derivation as `apply_event.py:55`; valid
    because no cards are played until bidding ends).
  - `bids = list(range(cards_dealt + 1))`; if `len(player_bids) == len(players) - 1`, remove
    `cards_dealt - sum(player_bids.values())` when it's within range. Mirrors the assert at
    `apply_event.py:51-60`.
  - Does NOT account for `RoundDef.forced_bid` (issue specifies the full range; forced bids stay
    a caller concern in `random_game.py`/server for now). Mention in docstring.
- `get_legal_cards(state: GameState, player: PlayerId) -> list[Card]`
  - Port of `random_game.legal_cards`: empty trick -> whole hand; led card is a `Joker` -> whole
    hand; else cards matching the led suit if any, otherwise whole hand. Read hand from
    `state.hand_state.player_hands[player]`, trick from `current_trick`. Return a new list
    (don't alias the hand). Keep the docstring note that a led Joker imposes no suit.
  - Does not check whether it's `player`'s turn (callers pair it with `get_next_actor`).
- `get_next_actor(state: GameState) -> PlayerId | None`
  - `None` if `config` or `hand_state` is `None` (no game yet / hand just finished and needs the
    next `Deal` / game over -- the caller distinguishes via `hand_index` vs `len(GAME_ROUNDS)`).
  - Assert `hand_state.dealer_id is not None`.
  - Bidding phase (`len(player_bids) < n`): `players[(dealer_idx + 1 + len(player_bids)) % n]`.
  - Play phase: leader = `current_trick[0][0]` if trick in progress, else
    `finished_tricks[-1][0]` if any, else player after dealer; next =
    `players[(leader_idx + len(current_trick)) % n]`.

### 3. New `tests/test_legal_actions.py`
Match `test_apply_event.py` style: hand-built `GameState`/`HandState`, `make_player`,
`build_deck`, `inline_snapshot.snapshot` for returned lists, `SuitedCard`/`Joker`/`CardId`.
- `get_legal_bids`: non-last bidder gets `0..cards_dealt`; last bidder gets range minus the
  forbidden value; last bidder where forbidden value is out of range (sum of bids already >
  cards_dealt) gets the full range; all-bid -> `[]`; 1-card hand edge case.
- `get_legal_cards`: empty trick -> full hand; follow suit when holding the led suit; void in
  led suit -> full hand; led Joker -> full hand; Joker in hand while following suit is not
  offered (Jokers aren't `SuitedCard`; matches ported behaviour); returned list isn't the hand
  object.
- `get_next_actor`: `None` before `NewGame`, `None` with no hand_state; first bidder is after
  dealer (including dealer wrap-around, e.g. dealer = last seat); last bidder is the dealer;
  first leader after dealer; mid-trick follows seat order with wrap-around; next trick led by
  previous winner (not by seat); `None` after the final card of a hand (state from `apply_event`).
- One end-to-end consistency test: run a small hand (3 players, 2 cards) through `apply_event`
  and assert before each event that `get_next_actor(state)` equals that event's `player_id`.
- Add a `Deal`-sets-`dealer_id` assertion (the updated `test_deal_*` snapshots cover this).

## Verification
From `packages/gulk-lib`:
1. `make update-snapshots` -> review the diff: only `dealer_id` additions in the 3 deal snapshots
   and the integration golden file (`tests/integration/__inline_snapshot__/`); no other changes.
2. `make test` -> everything passes, including `test_random_game`.
3. `make check` -> `pyrefly`, `ruff`, `pyright` all clean (watch for `ruff` rules on `assert`
   in non-test code, as `apply_event.py` already uses them).
4. Sanity: `uv run python scripts/random_game.py --seed 1` still runs (script untouched).
