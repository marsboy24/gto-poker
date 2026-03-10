"""
Chance-Sampling Monte Carlo Counterfactual Regret Minimization (MCCFR)
for post-flop poker solving.

Reference: Lanctot et al. (2009) "Monte Carlo Sampling for Regret Minimization
in Extensive Games"
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Tuple, Any, Optional

from .game_state import GameState
from .evaluator import evaluate_hand, equity


class CFRSolver:
    """
    Chance-sampling MCCFR solver for post-flop poker.

    Maintains:
      - cumulative_regrets[info_set][action] -> float
      - strategy_sums[info_set][action] -> float

    These are used to compute the average strategy (Nash equilibrium approximation).
    """

    def __init__(self) -> None:
        self.cumulative_regrets: Dict[str, Dict[str, float]] = {}
        self.strategy_sums: Dict[str, Dict[str, float]] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def solve(
        self,
        game_state: GameState,
        iterations: int = 1000,
        hero_hand: Optional[List[str]] = None,
        opponent_range: Optional[List[List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Run MCCFR for the given number of iterations and return the strategy.

        Args:
            game_state: The current post-flop game state.
            iterations: Number of MCCFR iterations.
            hero_hand: Hero's hole cards (for equity calculation).
            opponent_range: Opponent hand combos (for equity calculation).

        Returns:
            {
              'strategy': {action_name: frequency},
              'equity': float,
              'iterations': int,
            }
        """
        self.cumulative_regrets.clear()
        self.strategy_sums.clear()

        hero = game_state.hero_position

        for i in range(iterations):
            self._mccfr(game_state, hero, 1.0, 1.0)

        strategy = self._get_average_strategy(game_state, hero)

        # Compute equity estimate
        eq = 0.5
        if hero_hand and opponent_range:
            eq = equity(hero_hand, opponent_range, game_state.board, iterations=min(500, iterations))

        return {
            'strategy': strategy,
            'equity': round(eq, 4),
            'iterations': iterations,
        }

    def solve_streaming(
        self,
        game_state: GameState,
        total_iterations: int = 1000,
        report_every: int = 100,
        hero_hand: Optional[List[str]] = None,
        opponent_range: Optional[List[List[str]]] = None,
    ):
        """
        Generator that yields intermediate results every report_every iterations.
        Useful for WebSocket streaming.

        Yields:
            {'iteration': int, 'strategy': dict, 'equity': float}
        """
        self.cumulative_regrets.clear()
        self.strategy_sums.clear()

        hero = game_state.hero_position
        eq = 0.5

        for i in range(1, total_iterations + 1):
            self._mccfr(game_state, hero, 1.0, 1.0)

            if i % report_every == 0 or i == total_iterations:
                strategy = self._get_average_strategy(game_state, hero)
                # Compute equity only on final batch to save time
                if i == total_iterations and hero_hand and opponent_range:
                    eq = equity(hero_hand, opponent_range, game_state.board, iterations=300)

                yield {
                    'iteration': i,
                    'strategy': strategy,
                    'equity': round(eq, 4),
                }

    # -----------------------------------------------------------------------
    # Core MCCFR algorithm
    # -----------------------------------------------------------------------

    def _mccfr(
        self,
        state: GameState,
        hero: int,
        hero_reach: float,
        opp_reach: float,
    ) -> float:
        """
        Recursive chance-sampling MCCFR.

        Returns the expected utility for the hero from this state.
        """
        if state.is_terminal():
            return self._terminal_utility(state, hero)

        current_player = state._current_player()
        info_set_key = state.to_info_set_key(current_player)
        actions = state.legal_actions()

        if not actions:
            return self._terminal_utility(state, hero)

        action_names = [self._action_label(a) for a in actions]

        # Get current strategy via regret matching
        strategy = self._get_strategy(info_set_key, action_names)

        if current_player == hero:
            # Hero node: compute counterfactual values for each action
            action_utils: Dict[str, float] = {}
            node_util = 0.0

            for a, action in zip(action_names, actions):
                prob = strategy.get(a, 1.0 / len(actions))
                next_state = state.apply_action(action)
                action_utils[a] = self._mccfr(next_state, hero, hero_reach * prob, opp_reach)
                node_util += prob * action_utils[a]

            # Update regrets
            regrets = self.cumulative_regrets.setdefault(info_set_key, {a: 0.0 for a in action_names})
            for a in action_names:
                regrets[a] += opp_reach * (action_utils.get(a, 0.0) - node_util)

            # Update strategy sum (weighted by hero reach)
            strat_sum = self.strategy_sums.setdefault(info_set_key, {a: 0.0 for a in action_names})
            for a in action_names:
                strat_sum[a] += hero_reach * strategy.get(a, 1.0 / len(actions))

            return node_util

        else:
            # Opponent node: sample a single action (chance sampling)
            probs = [strategy.get(a, 1.0 / len(actions)) for a in action_names]
            chosen_idx = self._sample_action(probs)
            chosen_action = actions[chosen_idx]
            chosen_name = action_names[chosen_idx]
            chosen_prob = probs[chosen_idx]

            # Update opponent strategy sum
            strat_sum = self.strategy_sums.setdefault(info_set_key, {a: 0.0 for a in action_names})
            for a in action_names:
                strat_sum[a] += opp_reach * strategy.get(a, 1.0 / len(actions))

            next_state = state.apply_action(chosen_action)
            return self._mccfr(next_state, hero, hero_reach, opp_reach * chosen_prob)

    # -----------------------------------------------------------------------
    # Strategy helpers
    # -----------------------------------------------------------------------

    def _get_strategy(self, info_set_key: str, action_names: List[str]) -> Dict[str, float]:
        """
        Compute the current strategy using regret matching.
        Positive regrets are proportional to action probabilities.
        """
        regrets = self.cumulative_regrets.get(info_set_key, {})
        positive_regrets = {a: max(0.0, regrets.get(a, 0.0)) for a in action_names}
        total = sum(positive_regrets.values())

        if total > 0:
            return {a: positive_regrets[a] / total for a in action_names}
        else:
            # Uniform strategy
            uniform = 1.0 / len(action_names)
            return {a: uniform for a in action_names}

    def _get_average_strategy(self, state: GameState, hero: int) -> Dict[str, float]:
        """
        Return the average strategy at the root node (Nash equilibrium approximation).
        """
        info_set_key = state.to_info_set_key(hero)
        actions = state.legal_actions()
        action_names = [self._action_label(a) for a in actions]

        strat_sums = self.strategy_sums.get(info_set_key, {})
        total = sum(strat_sums.get(a, 0.0) for a in action_names)

        if total > 0:
            avg = {a: round(strat_sums.get(a, 0.0) / total, 4) for a in action_names}
        else:
            # Fallback: uniform
            uniform = round(1.0 / max(1, len(action_names)), 4)
            avg = {a: uniform for a in action_names}

        # Ensure it sums to 1.0
        s = sum(avg.values())
        if s > 0 and abs(s - 1.0) > 1e-6:
            avg = {a: round(v / s, 4) for a, v in avg.items()}

        return avg

    # -----------------------------------------------------------------------
    # Terminal utility
    # -----------------------------------------------------------------------

    def _terminal_utility(self, state: GameState, hero: int) -> float:
        """
        Compute the terminal utility for the hero.
        If hero folded: utility = -amount hero put in pot (approximated).
        If only hero remains: utility = pot - hero's contribution (not tracked here, approximate).
        """
        if hero not in state.active_players:
            # Hero folded — lost whatever was put in
            hero_contributions = sum(
                h['amount'] for h in state.betting_history
                if h.get('player') == hero and h.get('action') in ('call', 'bet', 'raise')
            )
            return -hero_contributions

        if len(state.active_players) == 1 and state.active_players[0] == hero:
            # Everyone else folded, hero wins pot
            return state.pot * 0.5  # simplified: assume hero started with half pot

        # Showdown: approximate utility based on pot share
        # In a real solver, this would use hand evaluation against opponent ranges
        n_active = len(state.active_players)
        if n_active == 0:
            return 0.0
        # Hero gets 1/n share of pot (simplified for solver internals)
        return (state.pot / n_active) - (state.pot / 2.0)

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    @staticmethod
    def _action_label(action: Dict[str, Any]) -> str:
        """Create a clean, human-readable string label for an action."""
        act = action.get('action', 'unknown')
        amount = float(action.get('amount', 0.0))

        if act in ('fold', 'check'):
            return act
        if act == 'call':
            return f"call {amount:.1f}bb" if amount > 0 else 'call'
        if act == 'bet':
            if amount > 0:
                return f"bet {amount:.1f}bb"
            return 'bet'
        if act == 'raise':
            if amount > 0:
                return f"raise {amount:.1f}bb"
            return 'raise'
        return act

    @staticmethod
    def _sample_action(probs: List[float]) -> int:
        """Sample an action index given a probability distribution."""
        r = random.random()
        cumulative = 0.0
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                return i
        return len(probs) - 1
