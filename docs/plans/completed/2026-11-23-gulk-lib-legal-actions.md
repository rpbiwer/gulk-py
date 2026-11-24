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

Step 2 consequence: `get_legal_cards` always allows Jokers, which `random_game.legal_cards`
doesn't (see below). When step 2 moves `random_game.py` and the integration test over to the
new module, random play can pick a Joker where it couldn't before. Expect the golden file to
change then and regenerate it. This contradicts the "passes unchanged" line in
`playable-ui.md`, which step 2 should update.


## Key finding: dealer is not recorded in state

`get_next_actor` must know turn order, but `GameState`/`HandState` don't store who dealt.
`Deal.dealer_id` is consumed by nobody in `apply_event` (see `apply_event.py:23`). Turn order in
`random_game.py` and the integration test is:

- Bidding: starts with the player after the dealer, proceeds in seat order
  (`config.players` order), dealer bids last.
- Trick play: first trick led by the player after the dealer; each later trick led by the
  previous trick's winner (`finished_tricks[-1][0]`); within a trick, seat order from the leader.

**Decision: don't add to state (YAGNI); infer the dealer from the round number.** The dealer of
hand `i` is `players[i % n]` (`random_game.py` rotates `dealer_index` once per hand), and
`GameState.hand_index` is already the current hand during bidding and play (it only increments
when a hand finishes, `apply_event.py:100`). Extract this as a small public helper in
`legal_actions.py`, `get_dealer_id(config: GameConfig, hand_index: int) -> PlayerId`, so the rule
lives in one place and `get_next_actor` (and later `random_game.py`, step 2) can reuse it. No
changes to `game_state.py`, `apply_event.py`, existing snapshots or the golden file.

## Implementation

### 1. New `legal_actions.py`
Follow repo style (plain functions). The queries take only what they conceptually need (game
config and/or the current `HandState`), not the full `GameState`. Callers pass
`state.config` / `state.hand_state` (asserting non-`None` on their side).

- `get_dealer_id(config: GameConfig, hand_index: int) -> PlayerId`
  - `config.players[hand_index % len(config.players)].id`. Docstring notes the rotation
    convention.
- `get_legal_bids(config: GameConfig, hand_state: HandState) -> list[int]`
  - Raise `ValueError` if everyone has already bid (not in bidding phase) rather than returning
    `[]`.
  - `cards_dealt = len(any player's hand)` (same derivation as `apply_event.py:55`; valid
    because no cards are played until bidding ends).
  - `bids = list(range(cards_dealt + 1))`; if `len(player_bids) == len(players) - 1`, remove
    `cards_dealt - sum(player_bids.values())` when it's within range. Mirrors the assert at
    `apply_event.py:51-60`.
  - Does NOT account for `RoundDef.forced_bid` (issue specifies the full range; forced bids stay
    a caller concern in `random_game.py`/server for now). Mention in docstring.
- `get_legal_cards(hand: list[Card], current_trick: Trick) -> list[Card]`
  - Based on `random_game.legal_cards`, with one deliberate change: **Jokers are always
    legal**. A Joker can be played at any time, whether or not the player could follow suit.
    Rules: empty trick -> whole hand; led card is a `Joker` -> whole hand; else if the player
    holds any card of the led suit -> those cards **plus every Joker in hand**; otherwise
    whole hand. Read hand from `hand_state.player_hands[player]`, trick from
    `current_trick`. Return a new list in hand order (don't alias the hand). The docstring
    says that a led Joker imposes no suit and that Jokers are exempt from follow-suit.
  - Existing behaviour contradicts this. `random_game.legal_cards` keeps only `SuitedCard`s
    of the led suit, so a player who can follow suit is never offered their Jokers. Nothing
    else enforces follow-suit (`apply_event.py:68` is still a TODO), so the script is the
    only place affected. This looks like a side effect of the `isinstance` filter, not an
    intended rule. `determine_trick_winner` already handles a Joker played anywhere in a
    trick (it wins outright), so no other code needs to change.
  - Does not check whether it's `player`'s turn (callers pair it with `get_next_actor`).
- `get_next_actor(config: GameConfig, hand_state: HandState, hand_index: int) -> PlayerId`
  - Dealer from `get_dealer_id(config, hand_index)`.
  - Bidding phase (`len(player_bids) < n`): `players[(dealer_idx + 1 + len(player_bids)) % n]`.
  - Play phase: leader = `current_trick[0][0]` if trick in progress, else
    `finished_tricks[-1][0]` if any, else player after dealer; next =
    `players[(leader_idx + len(current_trick)) % n]`.
  - Never returns `None`: `apply_event` sets `hand_state = None` once the last card of a hand is
    played, so a caller holding a `HandState` always has someone to act. "No hand in progress"
    (no game yet / between hands / game over) is the caller's concern, since it has no
    `hand_state` to pass.

### 3. New `tests/test_legal_actions.py`
Match `test_apply_event.py` style: hand-built `GameState`/`HandState`, `make_player`,
`build_deck`, `inline_snapshot.snapshot` for returned lists, `SuitedCard`/`Joker`/`CardId`.
- `get_dealer_id`: rotates with `hand_index` and wraps around.
- `get_legal_bids`: non-last bidder gets `0..cards_dealt`; last bidder gets range minus the
  forbidden value; last bidder where forbidden value is out of range (sum of bids already >
  cards_dealt) gets the full range; all-bid -> raises `ValueError`; 1-card hand edge case.
- `get_legal_cards`: empty trick -> full hand; follow suit when holding the led suit; void in
  led suit -> full hand; led Joker -> full hand; Joker in hand while able to follow suit is
  offered alongside the led-suit cards (and off-suit cards are not); returned list isn't the
  hand object.
- `get_next_actor`: first bidder is after
  dealer (including dealer wrap-around, e.g. dealer = last seat); last bidder is the dealer;
  first leader after dealer; mid-trick follows seat order with wrap-around; next trick led by
  previous winner (not by seat).
- One end-to-end consistency test: run a small hand (3 players, 2 cards) through `apply_event`
  and assert before each event that `get_next_actor(config, hand_state, hand_index)` equals that event's `player_id`.

## Verification
From `packages/gulk-lib`:
1. `make test` -> everything passes with no snapshot changes, including `test_random_game`.
2. `make check` -> `pyrefly`, `ruff`, `pyright` all clean (watch for `ruff` rules on `assert`
   in non-test code, as `apply_event.py` already uses them).
3. Sanity: `uv run python scripts/random_game.py --seed 1` still runs (script untouched).
