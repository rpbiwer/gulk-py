import pytest
from inline_snapshot import snapshot

from gulk_lib.apply_event import apply_event
from gulk_lib.cards import RANKS, Card, CardId, Joker, SuitedCard
from gulk_lib.events import Bid, GameEvent, NewGame, PlayCard
from gulk_lib.game_config import GameConfig
from gulk_lib.game_state import GameState, HandState, Trick
from gulk_lib.legal_actions import (
    get_dealer_id,
    get_legal_bids,
    get_legal_cards,
    get_next_actor,
)
from gulk_lib.player_id import PlayerId
from tests.factories import make_bid, make_deal, make_play_card, make_player

P1, P2, P3 = PlayerId("1"), PlayerId("2"), PlayerId("3")

SPADE_2 = SuitedCard(CardId(0), 2, "♠")
SPADE_3 = SuitedCard(CardId(1), 3, "♠")
SPADE_4 = SuitedCard(CardId(2), 4, "♠")
SPADE_5 = SuitedCard(CardId(3), 5, "♠")
SPADE_6 = SuitedCard(CardId(4), 6, "♠")
SPADE_7 = SuitedCard(CardId(5), 7, "♠")
HEART_2 = SuitedCard(CardId(13), 2, "♥")
DIAMOND_2 = SuitedCard(CardId(26), 2, "♦")
JOKER = Joker(CardId(52))


def make_config() -> GameConfig:
    return GameConfig([make_player(1), make_player(2), make_player(3)], jokers=2)


def make_hand_state(
    cards_per_player: int, player_bids: dict[PlayerId, int] | None = None
) -> HandState:
    return HandState(
        player_bids=player_bids or {},
        player_hands={
            P1: [SuitedCard(CardId(i), RANKS[i], "♠") for i in range(cards_per_player)],
            P2: [
                SuitedCard(CardId(13 + i), RANKS[i], "♥")
                for i in range(cards_per_player)
            ],
            P3: [
                SuitedCard(CardId(26 + i), RANKS[i], "♦")
                for i in range(cards_per_player)
            ],
        },
    )


ALL_BIDS = {P1: 0, P2: 0, P3: 0}


# get_dealer_id


def test_dealer_rotates_with_hand_index_and_wraps():
    config = make_config()
    assert [get_dealer_id(config, i) for i in range(5)] == snapshot(
        [PlayerId("1"), PlayerId("2"), PlayerId("3"), PlayerId("1"), PlayerId("2")]
    )


# get_legal_bids


def test_non_last_bidder_gets_full_range():
    hand_state = make_hand_state(3, {P2: 3})
    assert get_legal_bids(make_config(), hand_state) == [0, 1, 2, 3]


def test_first_bidder_gets_full_range():
    hand_state = make_hand_state(3)
    assert get_legal_bids(make_config(), hand_state) == [0, 1, 2, 3]


def test_last_bidder_cannot_make_bids_sum_to_cards_dealt():
    hand_state = make_hand_state(3, {P2: 1, P3: 1})
    assert get_legal_bids(make_config(), hand_state) == [0, 2, 3]


def test_last_bidder_gets_full_range_when_forbidden_value_out_of_range():
    hand_state = make_hand_state(3, {P2: 3, P3: 2})
    assert get_legal_bids(make_config(), hand_state) == [0, 1, 2, 3]


def test_one_card_hand():
    assert get_legal_bids(make_config(), make_hand_state(1)) == [0, 1]
    hand_state = make_hand_state(1, {P2: 0, P3: 0})
    assert get_legal_bids(make_config(), hand_state) == [0]


def test_legal_bids_raises_when_everyone_has_bid():
    hand_state = make_hand_state(3, {P1: 0, P2: 0, P3: 0})
    with pytest.raises(ValueError, match="all players have already bid"):
        get_legal_bids(make_config(), hand_state)


# get_legal_cards


def test_empty_trick_allows_whole_hand():
    hand: list[Card] = [SPADE_2, HEART_2, JOKER]
    assert get_legal_cards(hand, []) == [SPADE_2, HEART_2, JOKER]


def test_must_follow_suit_when_able():
    hand: list[Card] = [SPADE_3, HEART_2, DIAMOND_2, SPADE_4]
    assert get_legal_cards(hand, [(P1, SPADE_7)]) == [SPADE_3, SPADE_4]


def test_void_in_led_suit_allows_whole_hand():
    hand: list[Card] = [HEART_2, DIAMOND_2]
    assert get_legal_cards(hand, [(P1, SPADE_7)]) == [HEART_2, DIAMOND_2]


def test_led_joker_allows_whole_hand():
    hand: list[Card] = [SPADE_3, HEART_2]
    trick: Trick = [(P1, JOKER), (P3, SPADE_7)]
    assert get_legal_cards(hand, trick) == [SPADE_3, HEART_2]


def test_joker_is_legal_alongside_led_suit():
    hand: list[Card] = [SPADE_3, HEART_2, JOKER]
    assert get_legal_cards(hand, [(P1, SPADE_7)]) == [SPADE_3, JOKER]


def test_legal_cards_returns_new_list():
    hand: list[Card] = [SPADE_2, HEART_2]
    legal = get_legal_cards(hand, [])
    assert legal == hand
    assert legal is not hand


# get_next_actor


def test_first_bidder_is_after_dealer():
    hand_state = make_hand_state(2)
    assert get_next_actor(make_config(), hand_state, 0) == P2


def test_first_bidder_wraps_when_dealer_is_last_seat():
    hand_state = make_hand_state(2)
    assert get_next_actor(make_config(), hand_state, 2) == P1


def test_dealer_bids_last():
    hand_state = make_hand_state(2, {P2: 0, P3: 0})
    assert get_next_actor(make_config(), hand_state, 0) == P1


def test_first_leader_is_after_dealer():
    hand_state = make_hand_state(2, ALL_BIDS)
    assert get_next_actor(make_config(), hand_state, 1) == P3


def test_mid_trick_follows_seat_order_with_wraparound():
    hand_state = make_hand_state(2, ALL_BIDS)
    hand_state.current_trick = [(P3, DIAMOND_2)]
    assert get_next_actor(make_config(), hand_state, 1) == P1
    hand_state.current_trick = [(P3, DIAMOND_2), (P1, SPADE_2)]
    assert get_next_actor(make_config(), hand_state, 1) == P2


def test_next_trick_led_by_previous_winner():
    hand_state = make_hand_state(2, ALL_BIDS)
    # Dealer is P1, so P2 led the first trick, but P3 won it.
    hand_state.finished_tricks = [(P3, [(P2, HEART_2), (P3, JOKER), (P1, SPADE_2)])]
    assert get_next_actor(make_config(), hand_state, 0) == P3


def test_next_trick_led_by_most_recent_winner():
    hand_state = make_hand_state(3, ALL_BIDS)
    # Dealer is P1. P2 led the first trick and P3 won it; P3 led the second trick
    # and P1 won it, so P1 leads the third.
    hand_state.finished_tricks = [
        (P3, [(P2, HEART_2), (P3, JOKER), (P1, SPADE_2)]),
        (P1, [(P3, DIAMOND_2), (P1, SPADE_3), (P2, SPADE_4)]),
    ]
    assert get_next_actor(make_config(), hand_state, 0) == P1


def test_next_actor_matches_a_played_hand():
    config = make_config()
    state = GameState()
    apply_event(state, NewGame(config))

    # Hand 0 (dealer P1): P1 gets ♠ 2/3, P2 gets ♠ 4/5, P3 gets ♠ 6/7.
    apply_event(
        state,
        make_deal(
            [SPADE_2, SPADE_3, SPADE_4, SPADE_5, SPADE_6, SPADE_7],
            1,
            2,
            deal_trump=False,
        ),
    )
    events: list[GameEvent] = [
        make_bid(2, 1),
        make_bid(3, 0),
        make_bid(1, 0),
        make_play_card(2, 2),
        make_play_card(3, 4),  # P3 wins with ♠6
        make_play_card(1, 0),
        make_play_card(3, 5),
        make_play_card(1, 1),
        make_play_card(2, 3),
    ]
    for event in events:
        assert state.hand_state is not None
        assert isinstance(event, (Bid, PlayCard))
        assert get_next_actor(config, state.hand_state, state.hand_index) == (
            event.player_id
        )
        apply_event(state, event)

    assert state.hand_state is None
    assert state.hand_index == 1
