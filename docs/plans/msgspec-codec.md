# Plan: msgspec codec for gulk-lib events and cards (issue #4)

## Context

Step 3 of `docs/plans/playable-ui.md`. The Godot client and the future `gulk-server` need a wire format for `GameEvent` and `GameState`. Today `events.py` and `cards.py` are plain dataclasses and nothing can serialize them. This issue adds `packages/gulk-lib/src/gulk_lib/codec.py`, built on `msgspec`, and exposes `encode_event`, `decode_event`, `encode_state` and `decode_state`.

The issue refers to a `gulk_lib_deferred_event_serialization` memory. I couldn't find it in the repo or the runner environment. The plan below relies only on what the issue and the plan doc say. Where they leave a detail open, I list it under "Assumptions" so it's easy to overrule.

## Findings from exploring the code

- `cards.py`: `SuitedCard(id, rank, suit)` and `Joker(id)` are frozen dataclasses, and `Card = SuitedCard | Joker`. `Rank = Literal[2..10, "J","Q","K","A"]` mixes int and str. `CardSuit = Literal["♠","♥","♦","♣"]`. `CardId` and `PlayerId` are `NewType`s over `int` and `str`.
- `events.py`: `NewGame`, `Deal`, `Bid` and `PlayCard` are plain dataclasses, and `GameEvent` is their union. `NewGame.game_config` is a `GameConfig` dataclass, which stays a dataclass.
- `game_state.py`: `GameState` and `HandState` are dataclasses holding `dict[PlayerId, ...]`, `Trick = list[tuple[PlayerId, Card]]` and `trump: Card | None`. Per the issue they stay as dataclasses.
- `apply_event.py` uses positional `match` patterns (`case Deal(shuffled_deck, _, n, trump)`). `msgspec.Struct` defines `__match_args__`, so these should keep working. The test run will confirm it.
- Nothing in `src`, `tests` or `scripts` uses `dataclasses.replace`, `asdict` or `fields`. Converting the classes to Structs needs no call-site changes.
- **Golden-file churn**: `tests/integration/history.py::format_history` uses `pprint.pformat`. `pprint` wraps dataclasses over several lines but prints a Struct with plain `repr` on one line. The golden files under `tests/integration/__inline_snapshot__/` (`test_new_game`, `test_random_game`) will therefore change in whitespace only. A Struct `repr` (`SuitedCard(id=0, rank=2, suit='♠')`) has the same text as the dataclass repr.
- Project conventions: `uv` workspace, `ruff` with `select = ["ALL"]`, `pyrefly` and `pyright` in strict mode, pytest with `inline-snapshot`. Checks run through `make check` and `make test` in `packages/gulk-lib`.

## Assumptions (not fixed by the issue)

1. **Wire shape of `Rank` and suit.** The issue says the symbol-vs-letter and int/str mix need resolving, but doesn't state the target format. I chose:
   - Suit goes on the wire as `"S" | "H" | "D" | "C"`.
   - Rank goes on the wire as a string: `"2"`..`"10"`, `"J"`, `"Q"`, `"K"`, `"A"`. A uniform type is easier for GDScript than an int/str mix.
   - The in-memory types (`Rank`, `CardSuit`, `SUITS`, `RANKS`) don't change.
2. **Tag values.** I use explicit snake_case tags: `kind` is `"suited"` or `"joker"`, and `type` is `"new_game"`, `"deal"`, `"bid"` or `"play_card"`. The default class-name tags would also work. Only the constants in `events.py` and `cards.py` change if you prefer those.
3. **Error behaviour.** `decode_*` lets `msgspec.ValidationError` and `msgspec.DecodeError` propagate. Wrapping them is the server's job (step 5).

## Implementation steps

1. **Add the dependency.** From the repo root run `uv add msgspec --package gulk-lib`. This updates `packages/gulk-lib/pyproject.toml` and `uv.lock`. Don't edit `pyproject.toml` by hand.

2. **`cards.py`.**
   - Make `SuitedCard` a `msgspec.Struct, frozen=True, tag_field="kind", tag="suited"`. It keeps the fields `id`, `rank`, `suit` in the same order.
   - Make `Joker` a `msgspec.Struct, frozen=True, tag_field="kind", tag="joker"`.
   - Leave `Card = SuitedCard | Joker`, `Rank`, `CardSuit`, `SUITS` and `RANKS` as they are.

3. **`events.py`.**
   - Make `NewGame`, `Deal`, `Bid` and `PlayCard` Structs with `tag_field="type"` and the tags from assumption 2. They stay mutable, as the dataclasses are now. Keep the field order and types, so positional construction (as in `tests/factories.py`) and positional `match` patterns keep working.
   - Leave `GameEvent = NewGame | Deal | Bid | PlayCard` as it is.

4. **New `codec.py`.** It has two layers.
   - **Translation helpers.** These are pure functions over builtins (dict, list, str, int).
     - `_to_wire(node)` walks dicts and lists recursively. Wherever it finds a dict with `node["kind"] == "suited"`, it rewrites `suit` from symbol to letter and `rank` to `str(rank)`.
     - `_from_wire(node)` is the inverse. It maps letter back to symbol and rank string back to int when the string is all digits, otherwise it leaves it as `"J"`, `"Q"`, `"K"` or `"A"`.
     - The suit and rank tables derive from `SUITS` and `RANKS` in `cards.py`. A module-level assertion or a test checks that every suit and rank is covered, so adding a suit can't silently break the codec.
     - **The translation must be structure-aware.** It rewrites only dicts tagged `kind == "suited"`. It must not substitute strings blindly, because `PlayerId`s and player names can legitimately be `"S"`, `"A"`, `"10"` and so on.
   - **Public API.**
     - `encode_event(event: GameEvent) -> bytes` runs `msgspec.to_builtins`, then `_to_wire`, then `msgspec.json.encode`.
     - `decode_event(data: bytes | str) -> GameEvent` runs `msgspec.json.decode`, then `_from_wire`, then `msgspec.convert(..., GameEvent)`.
     - `encode_state(state: GameState) -> bytes` and `decode_state(data) -> GameState` do the same for `GameState`. msgspec handles the dataclasses natively.
   - No `enc_hook` or `dec_hook`. They don't fire for natively recognised `int` and `str` types, which is why the issue calls for the explicit translation step.
   - **Typing.** Passing a union alias such as `GameEvent` to `msgspec.convert` may not satisfy pyright strict. If so, use a small `cast` or a typed wrapper rather than a blanket ignore.
   - Both the encoding and decoding paths use `msgspec.convert` / `to_builtins`, so JSON and the Python-side builtins stay symmetric.

5. **Regenerate the golden files.** Run the existing integration tests with `fix` scoped to `tests/integration/` only. `fix` overwrites any mismatching snapshot it collects, so it must not run across the whole suite. See `tests/integration/CLAUDE.md`.
   - Before overwriting, copy the old golden files aside.
   - Then confirm the change is whitespace-only: `diff <(tr -d ' \n' < old) <(tr -d ' \n' < new)` must print nothing for each file.
   - If that diff isn't empty, stop and investigate, because it means the Struct conversion changed behaviour.

6. **Tests: new `tests/test_codec.py`.** It follows the existing style: `inline_snapshot`, and the helpers in `tests/factories.py`.
   - Round trip: for each event type, `decode_event(encode_event(e)) == e`. This includes a `Deal` over `build_deck(2)`, so Jokers are covered, and a `NewGame` with a `GameConfig`.
   - Wire-shape snapshots: `encode_event` of a small `Deal`, a `Bid` and a `PlayCard` against inline snapshots. They pin down the tags, the `S/H/D/C` letters, and string ranks including `"10"`.
   - All 52 suited cards plus a Joker survive encode and decode (`build_deck`).
   - **Collision regression:** a `NewGame` whose player ids and names are `"S"`, `"H"`, `"A"` and `"10"` round-trips unchanged. This guards the structure-aware translation.
   - State round trip: `decode_state(encode_state(s)) == s` for several states:
     - an empty `GameState()`;
     - after `NewGame`;
     - mid-hand, with `current_trick`, `finished_tricks`, a trump card and `player_bids` populated;
     - after a hand completes, with `hand_state is None` and scores set.
     - Build these by applying events through `apply_event`.
   - Error cases: an unknown `type` tag, a bad suit letter and a bad rank string each raise `msgspec.ValidationError`.

7. **Docs.** Add a sentence to `packages/gulk-lib/CLAUDE.md` or the README noting that `codec.py` is the wire boundary and that `events.py` and `cards.py` are Structs. This is optional. `docs/plans/playable-ui.md` is left alone, because plans move to `completed/` when the whole effort finishes, not per step.

## Files

- Modify: `packages/gulk-lib/src/gulk_lib/cards.py`, `packages/gulk-lib/src/gulk_lib/events.py`, `packages/gulk-lib/pyproject.toml` (via `uv add`) and `uv.lock`.
- Regenerate: `packages/gulk-lib/tests/integration/__inline_snapshot__/*/*.txt`.
- New: `packages/gulk-lib/src/gulk_lib/codec.py` and `packages/gulk-lib/tests/test_codec.py`.
- No changes to `game_state.py`, `game_config.py`, `player_id.py`, `apply_event.py` or `scripts/random_game.py`. This also avoids merge conflicts with issues #2 and #3, which touch `apply_event.py` and `random_game.py`.

## Verification

Run these from `packages/gulk-lib`:

1. `make check` runs `pyrefly`, `ruff` and `pyright`. Struct field types and the codec must pass strict mode.
2. `make test` runs the full suite. It must show:
   - `test_apply_event.py` and `test_determine_trick_winner.py` pass unchanged, which confirms that positional construction, `match` patterns, equality and `deepcopy` still work on Structs.
   - The integration tests pass against the regenerated golden files.
   - The new `test_codec.py` passes.
3. The whitespace-insensitive golden-file diff from step 5 is empty.
4. Spot check the full-game round trip. In a throwaway script, generate a game with `scripts/random_game.py::generate_random_game`. Then encode and decode every event and the final state, and assert equality with the originals. Don't commit this script.
5. Run `git diff pyproject.toml` and confirm `msgspec` is the only dependency change in `packages/gulk-lib/pyproject.toml`.
