"""
Hand evaluator using the treys library.
Provides equity estimation via Monte Carlo simulation.
"""

import random
from typing import List

from treys import Card, Evaluator


_evaluator = Evaluator()


def hand_to_treys(card_str: str) -> int:
    """
    Convert a card string in "As", "Kh", "2c" format to a treys Card integer.
    Treys expects the rank first, then suit in lowercase: 'As', 'Kh', '2c', 'Td'.
    """
    if len(card_str) != 2:
        raise ValueError(f"Invalid card string: {card_str!r}. Expected format like 'As', 'Kh', 'Td'.")
    rank = card_str[0]
    suit = card_str[1].lower()
    return Card.new(rank + suit)


def evaluate_hand(hole_cards: List[str], board: List[str]) -> int:
    """
    Evaluate a poker hand using treys.

    Args:
        hole_cards: List of 2 card strings, e.g. ["As", "Kh"]
        board: List of 3-5 board card strings, e.g. ["Qd", "Jc", "Ts"]

    Returns:
        Integer rank where lower is better (1 = royal flush, 7462 = 2-high).
    """
    treys_hole = [hand_to_treys(c) for c in hole_cards]
    treys_board = [hand_to_treys(c) for c in board]
    return _evaluator.evaluate(treys_board, treys_hole)


def _build_deck(exclude: List[str]) -> List[int]:
    """Build a standard 52-card deck excluding the specified cards."""
    all_ranks = '23456789TJQKA'
    all_suits = 'shdc'
    excluded_set = set()
    for c in exclude:
        excluded_set.add(hand_to_treys(c))

    deck = []
    for r in all_ranks:
        for s in all_suits:
            card = Card.new(r + s)
            if card not in excluded_set:
                deck.append(card)
    return deck


def equity(
    hole_cards: List[str],
    opponent_range: List[List[str]],
    board: List[str],
    iterations: int = 1000,
) -> float:
    """
    Monte Carlo equity estimate for hole_cards vs a range of opponent hands.

    Args:
        hole_cards: Hero's 2 hole cards, e.g. ["As", "Kh"]
        opponent_range: List of possible opponent hand combos, e.g. [["Qd","Jc"], ...]
        board: Current board cards (0-5 cards).
        iterations: Number of Monte Carlo samples.

    Returns:
        Equity as a float in [0.0, 1.0].
    """
    if not opponent_range:
        return 0.5

    cards_needed = 5 - len(board)
    wins = 0
    ties = 0
    total = 0

    known_cards = list(hole_cards) + list(board)

    for _ in range(iterations):
        # Pick a random opponent hand from range
        opp_hand = random.choice(opponent_range)

        # Skip if opponent cards conflict with known cards
        conflict = False
        for c in opp_hand:
            if c in known_cards:
                conflict = True
                break
        if conflict:
            continue

        # Build deck excluding all known cards
        exclude = known_cards + list(opp_hand)
        deck = _build_deck(exclude)

        if len(deck) < cards_needed:
            continue

        # Sample runout cards
        runout = random.sample(deck, cards_needed)

        # Convert runout to strings for evaluate_hand
        full_board_int = [hand_to_treys(c) for c in board] + runout
        # Evaluate using integer board directly
        hero_treys = [hand_to_treys(c) for c in hole_cards]
        opp_treys = [hand_to_treys(c) for c in opp_hand]

        hero_score = _evaluator.evaluate(full_board_int, hero_treys)
        opp_score = _evaluator.evaluate(full_board_int, opp_treys)

        if hero_score < opp_score:
            wins += 1
        elif hero_score == opp_score:
            ties += 1

        total += 1

    if total == 0:
        return 0.5

    return (wins + ties * 0.5) / total
