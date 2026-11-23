from gulk_lib.cards import Card, Joker, SuitedCard
from gulk_lib.game_config import GameConfig
from gulk_lib.game_state import HandState
from gulk_lib.player_id import PlayerId


def get_dealer_id(config: GameConfig, hand_index: int) -> PlayerId:
    """The dealer of hand `hand_index`.

    The deal rotates one seat (in `config.players` order) per hand, starting with
    the first player dealing hand 0.
    """
    return config.players[hand_index % len(config.players)].id


def get_legal_bids(config: GameConfig, hand_state: HandState) -> list[int]:
    """Legal bid values for the player whose turn it is to bid.

    Every bidder may bid anywhere from 0 to the number of cards dealt, except the
    last bidder, who may not make the bids sum to the number of cards dealt
    ("screw the dealer").

    Doesn't account for `RoundDef.forced_bid`; that's left to the caller.

    Raises `ValueError` if every player has already bid.
    """
    num_players = len(config.players)
    num_bids = len(hand_state.player_bids)
    if num_bids >= num_players:
        msg = "all players have already bid"
        raise ValueError(msg)

    # No cards are played until bidding ends, so any hand has the dealt count.
    any_player_hand = next(iter(hand_state.player_hands.values()))
    cards_dealt = len(any_player_hand)

    bids = list(range(cards_dealt + 1))
    if num_bids == num_players - 1:
        forbidden = cards_dealt - sum(hand_state.player_bids.values())
        if forbidden in bids:
            bids.remove(forbidden)
    return bids


def get_legal_cards(hand_state: HandState, player: PlayerId) -> list[Card]:
    """Cards from `player`'s hand that are legal to play into the current trick.

    Players must follow the led suit when they can. A led Joker has no suit, so it
    imposes no follow-suit constraint. Jokers are exempt from follow-suit: they may
    be played at any time.

    Doesn't check whether it's `player`'s turn; pair with `get_next_actor`.
    """
    hand = hand_state.player_hands[player]
    current_trick = hand_state.current_trick

    if len(current_trick) == 0:
        return list(hand)

    _, lead_card = current_trick[0]
    if isinstance(lead_card, Joker):
        return list(hand)

    can_follow_suit = any(
        isinstance(card, SuitedCard) and card.suit == lead_card.suit for card in hand
    )
    if not can_follow_suit:
        return list(hand)

    return [
        card for card in hand if isinstance(card, Joker) or card.suit == lead_card.suit
    ]


def get_next_actor(
    config: GameConfig, hand_state: HandState, hand_index: int
) -> PlayerId:
    """The player who must act next in the hand: the next bidder during bidding,
    otherwise the next player to play a card.

    Bidding starts with the player after the dealer and goes in seat order, so the
    dealer bids last. The first trick is led by the player after the dealer, each
    later trick by the previous trick's winner, and play within a trick goes in seat
    order from the leader.

    A `HandState` always has someone to act: `apply_event` clears it once the last
    card of the hand is played.
    """
    player_ids = [p.id for p in config.players]
    num_players = len(player_ids)
    dealer_index = player_ids.index(get_dealer_id(config, hand_index))

    num_bids = len(hand_state.player_bids)
    if num_bids < num_players:
        return player_ids[(dealer_index + 1 + num_bids) % num_players]

    current_trick = hand_state.current_trick
    if len(current_trick) > 0:
        leader = current_trick[0][0]
    elif len(hand_state.finished_tricks) > 0:
        leader = hand_state.finished_tricks[-1][0]
    else:
        leader = player_ids[(dealer_index + 1) % num_players]

    leader_index = player_ids.index(leader)
    return player_ids[(leader_index + len(current_trick)) % num_players]
