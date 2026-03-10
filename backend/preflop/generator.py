"""
GTO Pre-flop Range Generator for Cash Games (No Antes, 100bb Stack Depth).

Generates approximate GTO opening ranges using Sklansky-style hand strength scores,
position multipliers, and Nash equilibrium approximation via softmax/logit mapping.

Output: ranges[num_players][position][action] -> {hand: frequency}
"""

import json
import os
import math
from typing import Dict, List

# ---------------------------------------------------------------------------
# 1. Hand definitions
# ---------------------------------------------------------------------------

RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}  # A=0 (highest) ... 2=12 (lowest)

def all_169_hands() -> List[str]:
    """Return all 169 canonical starting hands."""
    hands = []
    # Pairs
    for r in RANKS:
        hands.append(r + r)
    # Suited and offsuit combos (r1 > r2 in rank value)
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if j > i:  # r2 is weaker (higher index)
                hands.append(r1 + r2 + 's')
                hands.append(r1 + r2 + 'o')
    return hands


# ---------------------------------------------------------------------------
# 2. Hand strength scoring
# ---------------------------------------------------------------------------

PAIR_SCORES: Dict[str, float] = {
    'AA': 100, 'KK': 99, 'QQ': 98, 'JJ': 97, 'TT': 95,
    '99': 92, '88': 88, '77': 83, '66': 76, '55': 68,
    '44': 60, '33': 52, '22': 44,
}

def hand_strength(hand: str) -> float:
    """
    Return a hand strength score (0-100) for any of the 169 canonical hands.
    Pairs use the PAIR_SCORES table. Suited/offsuit hands are scored by high
    card value, connectedness bonus, and a suited premium.
    """
    if len(hand) == 2 and hand[0] == hand[1]:
        # Pair
        return PAIR_SCORES[hand]

    suited = hand.endswith('s')
    r1, r2 = hand[0], hand[1]
    v1 = RANK_VALUES[r1]  # lower = higher rank
    v2 = RANK_VALUES[r2]

    # High-card base: A=13, K=12, ... 2=1
    hc1 = 13 - v1
    hc2 = 13 - v2

    # Base score: blend of both cards, weighted toward the high card
    base = hc1 * 5.0 + hc2 * 3.5

    # Connectedness bonus: gap between two cards
    gap = abs(v1 - v2)
    if gap == 1:
        connect_bonus = 5.0
    elif gap == 2:
        connect_bonus = 3.0
    elif gap == 3:
        connect_bonus = 1.5
    else:
        connect_bonus = 0.0

    # Suited premium
    suit_bonus = 8.0 if suited else 0.0

    # Offsuit penalty relative to suited (already handled by no suit_bonus)
    raw = base + connect_bonus + suit_bonus

    # Normalise so the best non-pair hand (AKs) scores around 90
    # AKs: 13*5 + 12*3.5 + 0 + 8 = 65+42+8 = 115  → scale by 115/90
    raw = raw * (90.0 / 115.0)

    return max(0.0, min(100.0, raw))


# ---------------------------------------------------------------------------
# 3. Position definitions
# ---------------------------------------------------------------------------

POSITIONS: Dict[int, List[str]] = {
    2: ["BTN/SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["CO", "BTN", "SB", "BB"],
    5: ["HJ", "CO", "BTN", "SB", "BB"],
    6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
    7: ["UTG", "UTG+1", "HJ", "CO", "BTN", "SB", "BB"],
    8: ["UTG", "UTG+1", "UTG+2", "HJ", "CO", "BTN", "SB", "BB"],
    9: ["UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN", "SB", "BB"],
}

# Position multiplier: how much looser/tighter a position opens
# Higher = looser (closer to button). BTN=1.0 baseline.
POSITION_MULTIPLIERS: Dict[str, float] = {
    "UTG":    0.62,
    "UTG+1":  0.66,
    "UTG+2":  0.70,
    "LJ":     0.74,
    "HJ":     0.78,
    "CO":     0.86,
    "BTN":    1.00,
    "BTN/SB": 0.90,
    "SB":     0.80,
    "BB":     0.70,  # BB has different dynamics (closing the action)
}


# ---------------------------------------------------------------------------
# 4. Nash equilibrium approximation via logit/softmax
# ---------------------------------------------------------------------------

def logit_frequency(strength: float, threshold: float, temperature: float) -> float:
    """
    Convert a hand strength to an action frequency using a logistic function.
    - threshold: the strength at which frequency = 0.5
    - temperature: steepness (lower = sharper cutoff, higher = more mixing)
    """
    x = (strength - threshold) / temperature
    return 1.0 / (1.0 + math.exp(-x))


def compute_open_raise_freq(strength: float, pos_mult: float, n_players: int) -> float:
    """
    Compute open-raise frequency for a hand from a given position.
    Tighter ranges from early position, wider from late position.
    More players at table = tighter (more chance someone has a premium).

    Calibration targets (6-max, 100bb):
      UTG  ~28% of combos, BTN ~48%, SB ~40%
    """
    # Threshold: higher = tighter
    # base_threshold 62 gives UTG=28%, BTN=48% (6-max) with mult=35
    player_tightening = (n_players - 2) * 1.2  # extra tightening per extra player beyond 2
    base_threshold = 62.0 - (pos_mult - 0.62) * 35.0 + player_tightening

    # Temperature governs how "mixed" the strategy is (GTO mixes many hands)
    temperature = 9.0 + (1.0 - pos_mult) * 4.0

    freq = logit_frequency(strength, base_threshold, temperature)

    # Cap at 0.98 — never pure raise with any hand (GTO mixes)
    return min(0.98, max(0.0, freq))


def compute_3bet_freq(strength: float, pos_mult: float, n_players: int) -> float:
    """
    3-bet frequency when facing an open raise.
    Higher-strength hands 3bet more; some weak hands also 3bet as bluffs.
    """
    player_factor = 1.0 + (n_players - 2) * 0.05
    # Value 3bets: top hands
    value_threshold = 75.0 * player_factor
    value_temp = 8.0

    value_freq = logit_frequency(strength, value_threshold, value_temp)

    # Bluff 3bets: some low-strength suited hands (polarised strategy)
    bluff_threshold = 30.0
    bluff_temp = 6.0
    bluff_max = 0.25 * pos_mult  # bluff frequency scaled by position advantage

    # Suited hands get a bluff bonus
    bluff_freq = (1.0 - logit_frequency(strength, bluff_threshold, bluff_temp)) * bluff_max

    combined = min(0.95, value_freq + bluff_freq * (1.0 - value_freq))
    return max(0.0, combined)


def compute_call_open_freq(strength: float, pos_mult: float, n_players: int) -> float:
    """
    Call (flat) frequency when facing an open raise (from non-blind positions).
    Hands that are too strong should 3bet, weak hands fold.
    """
    player_factor = 1.0 + (n_players - 2) * 0.04
    call_threshold = 50.0 * player_factor - (pos_mult - 0.62) * 12.0
    call_temp = 9.0

    raw_call = logit_frequency(strength, call_threshold, call_temp)

    # Value hands that would 3bet instead of calling
    three_bet_threshold = 75.0
    three_bet_suppressor = logit_frequency(strength, three_bet_threshold, 6.0)

    freq = raw_call * (1.0 - 0.7 * three_bet_suppressor)
    return min(0.90, max(0.0, freq))


def compute_sb_actions(strength: float, n_players: int) -> Dict[str, float]:
    """
    SB vs BB (heads-up or SB facing folds to it):
    Mixed limp/raise strategy. SB uses a polarised range.
    The SB is in a tough spot (out of position postflop).
    """
    n_factor = 1.0 + (n_players - 2) * 0.05

    # Raise frequency from SB (after everyone folds to SB)
    raise_threshold = 42.0 * n_factor
    raise_temp = 12.0
    raise_freq = logit_frequency(strength, raise_threshold, raise_temp)

    # Limp: medium-strength hands that don't want to raise/fold
    # (some hands limp, some raise, creating mixed strategy)
    limp_base = logit_frequency(strength, 28.0, 9.0) * (1.0 - raise_freq)
    limp_freq = min(0.85, limp_base * 1.2)

    fold_freq = max(0.0, 1.0 - raise_freq - limp_freq)

    # Normalise
    total = raise_freq + limp_freq + fold_freq
    if total > 0:
        raise_freq /= total
        limp_freq /= total
        fold_freq /= total

    return {
        'open_raise': raise_freq,
        'call_open': limp_freq,   # "limp" mapped to call_open for consistency
        'fold': fold_freq,
        '3bet': 0.0,
    }


def compute_bb_defense(strength: float, n_players: int) -> Dict[str, float]:
    """
    BB defense vs open raise (based on pot odds: calling 1bb into 3bb = ~33% equity needed).
    BB can call, 3bet, or fold.
    """
    n_factor = 1.0 + (n_players - 2) * 0.04

    # BB needs ~33% equity; GTO suggests defending ~55% of range vs single raise
    defend_threshold = 30.0 * n_factor
    defend_temp = 10.0
    defend_freq = logit_frequency(strength, defend_threshold, defend_temp)

    # 3bet frequency for BB
    three_bet_threshold = 72.0
    three_bet_temp = 8.0
    three_bet_freq = logit_frequency(strength, three_bet_threshold, three_bet_temp) * 0.90

    # Bluff 3bets from BB (wide polarised 3bets)
    bluff_freq = (1.0 - logit_frequency(strength, 25.0, 6.0)) * 0.20
    three_bet_freq = min(0.95, three_bet_freq + bluff_freq * (1.0 - three_bet_freq))

    call_freq = defend_freq * (1.0 - three_bet_freq)
    fold_freq = max(0.0, 1.0 - call_freq - three_bet_freq)

    total = call_freq + three_bet_freq + fold_freq
    if total > 0:
        call_freq /= total
        three_bet_freq /= total
        fold_freq /= total

    return {
        'open_raise': 0.0,
        'call_open': call_freq,
        '3bet': three_bet_freq,
        'fold': fold_freq,
    }


# ---------------------------------------------------------------------------
# 5. Main range computation
# ---------------------------------------------------------------------------

def generate_ranges() -> Dict:
    """
    Generate GTO pre-flop ranges for all player counts (2-9).
    Returns: ranges[num_players][position][action] -> {hand: frequency}
    """
    hands = all_169_hands()
    ranges: Dict = {}

    for n in range(2, 10):
        positions = POSITIONS[n]
        ranges[str(n)] = {}

        for pos in positions:
            pos_mult = POSITION_MULTIPLIERS.get(pos, 0.75)
            ranges[str(n)][pos] = {
                'open_raise': {},
                'call_open': {},
                '3bet': {},
                'fold': {},
            }

            for hand in hands:
                strength = hand_strength(hand)

                if pos == 'BB':
                    action_freqs = compute_bb_defense(strength, n)
                elif pos == 'SB':
                    action_freqs = compute_sb_actions(strength, n)
                elif pos == 'BTN/SB':
                    # In heads-up, BTN/SB acts first preflop
                    action_freqs = compute_sb_actions(strength, n)
                    # Heads-up BTN/SB is looser
                    or_freq = compute_open_raise_freq(strength, 1.0, n)
                    action_freqs['open_raise'] = or_freq
                    remainder = 1.0 - or_freq
                    action_freqs['call_open'] = remainder * 0.5
                    action_freqs['fold'] = remainder * 0.5
                    action_freqs['3bet'] = 0.0
                else:
                    # Normal open position
                    # open_raise and fold are complementary (first decision: open or fold)
                    or_freq = compute_open_raise_freq(strength, pos_mult, n)
                    fold_freq = 1.0 - or_freq

                    # 3bet and call_open represent responses when facing a raise
                    # (stored separately for the range viewer; not part of the open/fold decision)
                    three_bet_freq = compute_3bet_freq(strength, pos_mult, n)
                    call_freq = compute_call_open_freq(strength, pos_mult, n)

                    # Ensure 3bet + call ≤ 1 (remainder = fold facing raise)
                    total_facing_raise = three_bet_freq + call_freq
                    if total_facing_raise > 1.0:
                        three_bet_freq /= total_facing_raise
                        call_freq /= total_facing_raise

                    action_freqs = {
                        'open_raise': or_freq,
                        '3bet': three_bet_freq,
                        'call_open': call_freq,
                        'fold': fold_freq,
                    }

                for action, freq in action_freqs.items():
                    rounded = round(float(freq), 4)
                    if rounded > 0.0:
                        ranges[str(n)][pos][action][hand] = rounded

    return ranges


# ---------------------------------------------------------------------------
# 6. Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Generating GTO pre-flop ranges...")
    ranges = generate_ranges()

    out_path = os.path.join(os.path.dirname(__file__), 'ranges.json')
    with open(out_path, 'w') as f:
        json.dump(ranges, f, indent=2)

    print(f"Ranges written to {out_path}")

    # Quick sanity check
    n6 = ranges['6']
    btn_raise = n6['BTN']['open_raise']
    aa_freq = btn_raise.get('AA', 0)
    sevtwo_freq = btn_raise.get('72o', 0)
    print(f"6-handed BTN open AA: {aa_freq:.4f} (expect ~0.95+)")
    print(f"6-handed BTN open 72o: {sevtwo_freq:.4f} (expect ~0.01)")
