# Step 1: gulk-lib Legal-Move Queries

This document details the implementation of the first step in the playable UI roadmap: adding legal-move query functions to `gulk-lib`.

## Context

From `/docs/plans/playable-ui.md`:

> Step 1: **`gulk-lib`: legal-move queries.** Add `get_legal_bids`, `get_legal_cards`, `get_next_actor` to a new `legal_actions.py`, plus unit tests.

These functions are the foundation of both:
- The playable UI (to highlight valid actions)
- The bot engine (to pick valid moves automatically)

Current state:
- `scripts/random_game.py` has ad-hoc `legal_cards()` logic (lines 53-73) and `_random_bid()` logic (lines 76-88)
- `apply_event.py` has a TODO at line 68 to enforce follow-suit
- No centralized legal-move authority exists in `gulk-lib`

## Implementation Plan

### 1. Create `legal_actions.py` module

**Location:** `packages/gulk-lib/src/gulk_lib/legal_actions.py`

#### `get_legal_bids(state: GameState) -> list[int]`

Returns the set of legal bid values for the current bidder.

**Logic:**
1. Determine whose turn it is to bid using the bidder rotation pattern:
   - Bidding starts with the player after the dealer
   - Order proceeds clockwise around the table
2. Get `cards_dealt` from the current `RoundDef` using `state.hand_index`
3. If this is NOT the final bidder:
   - Return `list(range(0, cards_dealt + 1))`
4. If this IS the final bidder:
   - Calculate `current_sum = sum(state.hand_state.player_bids.values())`
   - `forbidden = cards_dealt - current_sum`
   - Return `[n for n in range(0, cards_dealt + 1) if n != forbidden]`
5. Handle `forced_bid` rounds (from `RoundDef.forced_bid`):
   - If set and the forced value is not forbidden, only that value is legal

**Edge cases:**
- Returns empty list if bidding is complete (e.g., all players have bid)
- Returns empty list if no hand is active (`state.hand_state is None`)

#### `get_legal_cards(state: GameState, player: PlayerId) -> list[Card]`

Returns the follow-suit-filtered legal plays for a given player.

**Logic:**
1. Get the player's hand from `state.hand_state.player_hands[player]`
2. Get the current trick from `state.hand_state.current_trick`
3. If `current_trick` is empty (player is leading):
   - Return full hand
4. Otherwise, get the lead card (`current_trick[0][1]`):
   - If lead is `Joker`: return full hand (Joker has no suit to follow)
   - If lead is `SuitedCard`: filter hand to cards of matching suit
   - If filtered list is non-empty: return it
   - If empty (player is void in led suit): return full hand

**Edge cases:**
- Returns empty list if player has no cards
- Raises `KeyError` if player not in hand (should not happen in valid game state)

#### `get_next_actor(state: GameState) -> PlayerId | None`

Returns whose turn it is to act, or `None` if no action needed.

**Logic:**
1. If `state.hand_state is None`:
   - If `state.hand_index >= len(GAME_ROUNDS)`: game is over → return `None`
   - Otherwise: waiting for `Deal` event → return dealer for next hand
2. If bidding incomplete:
   - Calculate expected number of bids = number of players
   - If `len(player_bids) < num_players`: return next bidder in rotation
3. If bidding complete but cards remain in hands:
   - If `current_trick` incomplete: return next player in trick rotation
   - Otherwise: return leader for next trick (winner of last finished trick)
4. If hands empty (hand finished): return `None` (needs `Deal` for next hand)

**Bidding order calculation:**
- Dealer is inferred from `state.hand_index` rotation
- First bidder = player after dealer
- Use `state.config.players` list order for rotation

### 2. Update `apply_event.py`

Replace the follow-suit TODO at line 68 with validation using `get_legal_cards`.

**Changes:**
1. Import `get_legal_cards` from `legal_actions`
2. Replace lines 68-70 comment with actual validation:
   ```python
   legal = get_legal_cards(state, player_id)
   assert card in legal, f"{card} is not a legal play; must follow suit"
   ```

Note: Keep this as an assertion (not a typed exception) - it's an internal invariant violation if the caller validated first. `gulk-server` will catch and translate these to wire errors.

### 3. Update `scripts/random_game.py`

Refactor to use the new centralized `legal_actions` module.

**Changes:**
1. Import `get_legal_bids`, `get_legal_cards` from `gulk_lib.legal_actions`
2. Remove the local `legal_cards()` function (lines 53-73)
3. Refactor `_random_bid()` to use `get_legal_bids()`:
   - Call `get_legal_bids()` instead of calculating forbidden value manually
   - Pick from the returned legal list (maintain triangular distribution preference)
4. Update `generate_random_game()`:
   - Replace `legal_cards(hand, state.hand_state.current_trick)` call
   - With `get_legal_cards(state, player_id)`

### 4. Unit Tests

Create `packages/gulk-lib/tests/test_legal_actions.py`

#### `test_get_legal_bids_for_non_dealer`
- 3-player game, first 2 bidders
- Should return full range `0..cards_dealt`

#### `test_get_legal_bids_for_dealer_screw_dealer_constraint`
- 4 players, first 3 have bid 0, 1, 2 in a 5-card hand (sum = 3)
- Dealer's legal bids should exclude 2 (since 3+2 = 5)

#### `test_get_legal_bids_empty_when_bidding_done`
- All players have bid
- Should return empty list

#### `test_get_legal_bids_forced_bid`
- Round with `forced_bid=3`
- Should return `[3]` (or empty if 3 is forbidden)

#### `test_get_legal_cards_when_leading`
- Empty trick, player has hand
- Should return full hand

#### `test_get_legal_cards_follow_suit_when_possible`
- Current trick led with ♠, player has ♠A and ♥K
- Should return only ♠A

#### `test_get_legal_cards_can_play_any_when_void`
- Current trick led with ♠, player has only ♥ and ♦
- Should return full hand

#### `test_get_legal_cards_joker_lead_allows_anything`
- Current trick led with Joker
- Should return full hand

#### `test_get_legal_cards_empty_when_no_cards`
- Player has empty hand
- Should return empty list

#### `test_get_next_actor_returns_first_bidder`
- Just dealt, no bids yet
- Should return player after dealer

#### `test_get_next_actor_returns_none_when_game_over`
- `hand_index == 20` (all rounds played)
- Should return `None`

#### `test_get_next_actor_returns_trick_leader_when_new_trick`
- Bidding done, start of first trick
- Should return first trick leader (player after dealer)

#### `test_get_next_actor_returns_trick_winner_for_next_trick`
- One trick finished, 2-player game
- Should return the winner of that trick

### 5. Integration Test Updates

Update `tests/integration/test_integration.py` to use `legal_actions` instead of ad-hoc logic.

**Changes:**
- If the integration test's random-play loop has local legal-move logic, replace with calls to `get_legal_bids`/`get_legal_cards`
- The golden-file test (`test_random_game`) should pass unchanged since behavior is equivalent

### 6. Run Full Test Suite

```bash
cd packages/gulk-lib
uv run pytest tests/ -v
uv run pytest tests/integration/ -v
```

All tests should pass, including the existing integration test golden file.

## Files Changed

1. **NEW:** `packages/gulk-lib/src/gulk_lib/legal_actions.py`
2. **MODIFIED:** `packages/gulk-lib/src/gulk_lib/apply_event.py` - replace TODO with validation
3. **MODIFIED:** `scripts/random_game.py` - use new module
4. **NEW:** `packages/gulk-lib/tests/test_legal_actions.py`
5. **MODIFIED:** `packages/gulk-lib/tests/integration/test_integration.py` (if needed)

## Dependencies

No new dependencies. Uses existing:
- `gulk_lib.game_state`
- `gulk_lib.game_rounds`
- `gulk_lib.cards`
- `gulk_lib.player_id`

## Verification Checklist

- [ ] `get_legal_bids` correctly handles screw-the-dealer constraint
- [ ] `get_legal_bids` returns empty list when no bid needed
- [ ] `get_legal_cards` enforces follow-suit
- [ ] `get_legal_cards` allows any card when void
- [ ] `get_legal_cards` allows any card after Joker lead
- [ ] `get_next_actor` returns correct player during bidding
- [ ] `get_next_actor` returns correct player during trick play
- [ ] `get_next_actor` returns `None` when hand/game complete
- [ ] `apply_event` validates with `get_legal_cards` (follow-suit enforced)
- [ ] `scripts/random_game.py` still generates valid games
- [ ] Integration test `test_random_game` passes with unchanged golden file
- [ ] All new code has unit tests with `inline-snapshot`
