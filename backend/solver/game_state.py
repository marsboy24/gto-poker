"""
GameState dataclass for post-flop solving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import copy


@dataclass
class GameState:
    players: int
    stacks: List[float]       # in bb
    pot: float                # in bb
    board: List[str]          # e.g. ["As", "Kh", "2c"]
    street: str               # "flop", "turn", "river"
    hero_position: int        # index in [0, players-1]
    betting_history: List[Dict[str, Any]]  # [{player, action, amount}]
    active_players: List[int]

    # Internal tracking (not set by user)
    current_player_idx: int = field(default=0)
    current_bet: float = field(default=0.0)
    last_aggressor: Optional[int] = field(default=None)
    players_acted_this_round: int = field(default=0)

    # -----------------------------------------------------------------------
    # Derived helpers
    # -----------------------------------------------------------------------

    def _num_active(self) -> int:
        return len(self.active_players)

    def _player_stack(self, player: int) -> float:
        if player < len(self.stacks):
            return self.stacks[player]
        return 0.0

    def _current_player(self) -> int:
        """Return the actual player index whose turn it is."""
        active = self.active_players
        if not active:
            return -1
        return active[self.current_player_idx % len(active)]

    # -----------------------------------------------------------------------
    # legal_actions
    # -----------------------------------------------------------------------

    def legal_actions(self) -> List[Dict[str, Any]]:
        """
        Return the list of legal actions for the current player.
        Each action is a dict with keys: action (str), amount (float, optional).

        Actions:
          - fold
          - check (when no bet to call)
          - call (when there is a bet to call)
          - raise (with min/max amounts)
        """
        player = self._current_player()
        stack = self._player_stack(player)
        actions: List[Dict[str, Any]] = []

        # Fold is always available (unless no bet, where check is free)
        if self.current_bet > 0:
            actions.append({'action': 'fold', 'amount': 0.0})

        if self.current_bet == 0:
            # Check
            actions.append({'action': 'check', 'amount': 0.0})
        else:
            # Call
            call_amount = min(self.current_bet, stack)
            actions.append({'action': 'call', 'amount': round(call_amount, 2)})

        # Raise (or bet if no current bet)
        # Min raise: 2x the current bet (or min bet = 1bb)
        if stack > self.current_bet:
            if self.current_bet == 0:
                # Bet: min 1bb, max stack
                min_bet = min(1.0, stack)
                half_pot = round(self.pot * 0.5, 2)
                pot_bet = round(self.pot, 2)
                sizes = sorted(set([min_bet, half_pot, pot_bet, stack]))
                for size in sizes:
                    if min_bet <= size <= stack:
                        label = 'all-in' if size == stack else f'bet_{size}bb'
                        actions.append({'action': 'bet', 'amount': round(size, 2), 'label': label})
            else:
                # Raise: min = 2x current bet, max = stack
                min_raise = min(self.current_bet * 2.0, stack)
                pot_raise = round(self.pot + self.current_bet * 2, 2)
                sizes = sorted(set([min_raise, pot_raise, stack]))
                for size in sizes:
                    if min_raise <= size <= stack:
                        label = 'all-in' if size == stack else f'raise_{size}bb'
                        actions.append({'action': 'raise', 'amount': round(size, 2), 'label': label})

        return actions

    # -----------------------------------------------------------------------
    # is_terminal
    # -----------------------------------------------------------------------

    def is_terminal(self) -> bool:
        """
        The game state is terminal if:
        1. Only one player remains active (everyone else folded).
        2. All streets have been played (river action complete).
        3. All active players are all-in.
        """
        if self._num_active() <= 1:
            return True

        # All active players are all-in (stacks == 0)
        all_in = all(self._player_stack(p) == 0.0 for p in self.active_players)
        if all_in:
            return True

        # River betting is complete: everyone has acted and bets are even
        if self.street == 'river' and self._betting_round_complete():
            return True

        return False

    def _betting_round_complete(self) -> bool:
        """Check if all active players have acted and bets are square."""
        if self._num_active() == 0:
            return True
        # All players have had a chance to act and no pending bets
        return (
            self.players_acted_this_round >= self._num_active()
            and self.current_bet == 0.0
        )

    # -----------------------------------------------------------------------
    # apply_action
    # -----------------------------------------------------------------------

    def apply_action(self, action: Dict[str, Any]) -> 'GameState':
        """
        Return a new GameState with the action applied.
        Does not mutate self.
        """
        new = copy.deepcopy(self)
        player = new._current_player()
        act = action.get('action', '')
        amount = float(action.get('amount', 0.0))

        if act == 'fold':
            new.active_players.remove(player)
            new.betting_history.append({'player': player, 'action': 'fold', 'amount': 0.0})
            # Adjust current_player_idx (it was pointing at this player)
            if new._num_active() > 0:
                new.current_player_idx = new.current_player_idx % new._num_active()
            new.players_acted_this_round += 1

        elif act == 'check':
            new.betting_history.append({'player': player, 'action': 'check', 'amount': 0.0})
            new.current_player_idx = (new.current_player_idx + 1) % max(1, new._num_active())
            new.players_acted_this_round += 1

        elif act == 'call':
            call_amount = min(new.current_bet, new._player_stack(player))
            new.stacks[player] = max(0.0, new.stacks[player] - call_amount)
            new.pot += call_amount
            new.betting_history.append({'player': player, 'action': 'call', 'amount': call_amount})
            new.current_player_idx = (new.current_player_idx + 1) % max(1, new._num_active())
            new.players_acted_this_round += 1

        elif act in ('bet', 'raise'):
            new.stacks[player] = max(0.0, new.stacks[player] - amount)
            new.pot += amount
            new.current_bet = amount
            new.last_aggressor = player
            new.players_acted_this_round = 1  # Reset: others need to respond
            new.betting_history.append({'player': player, 'action': act, 'amount': amount})
            new.current_player_idx = (new.current_player_idx + 1) % max(1, new._num_active())

        # Advance to next street if round is complete
        if new._betting_round_complete() and not new.is_terminal():
            new = new._advance_street()

        return new

    def _advance_street(self) -> 'GameState':
        """Advance to the next street, resetting betting state."""
        street_order = ['flop', 'turn', 'river']
        try:
            idx = street_order.index(self.street)
            next_street = street_order[idx + 1] if idx + 1 < len(street_order) else 'river'
        except ValueError:
            next_street = 'flop'

        new = copy.deepcopy(self)
        new.street = next_street
        new.current_bet = 0.0
        new.players_acted_this_round = 0
        new.last_aggressor = None
        # First to act post-flop is first active player after dealer (simplified: position 0)
        new.current_player_idx = 0
        return new

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def to_info_set_key(self, player: int) -> str:
        """Return a string key representing the information set for a player."""
        history_str = ','.join(
            f"{h['player']}:{h['action']}:{h['amount']}"
            for h in self.betting_history
        )
        return f"p{player}|{self.street}|{''.join(self.board)}|{history_str}"
