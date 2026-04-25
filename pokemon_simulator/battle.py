from __future__ import annotations

from dataclasses import dataclass, field
import random

from .models import MegaEvolution, Move, Pokemon, Priority, VZ


@dataclass
class BattlePokemon:
    """バトル中に使うポケモンインスタンス。"""

    source: Pokemon
    current_hp: int | None = None
    has_entered_battle: bool = False

    def __post_init__(self) -> None:
        if self.source.real_stats is None:
            self.source.calculate_and_assign_real_stats()
        if self.current_hp is None:
            self.current_hp = int(self.source.real_stats.values[0])

    @property
    def fainted(self) -> bool:
        return self.current_hp is not None and self.current_hp <= 0

    @property
    def speed(self) -> int:
        if self.source.real_stats is None:
            self.source.calculate_and_assign_real_stats()
        return int(self.source.real_stats.values[5])

    def receive_damage(self, amount: int) -> None:
        if self.current_hp is None:
            return
        self.current_hp = max(0, self.current_hp - max(0, int(amount)))


@dataclass
class TeamState:
    """6体チームの状態。"""

    party: list[BattlePokemon]
    selected_indices: list[int] = field(default_factory=list)
    active_index: int | None = None

    def choose_three(self, indices: list[int]) -> None:
        if len(indices) != 3:
            raise ValueError("選出は3体である必要があります。")
        if len(set(indices)) != 3:
            raise ValueError("選出インデックスが重複しています。")
        if any(i < 0 or i >= len(self.party) for i in indices):
            raise IndexError("選出インデックスが範囲外です。")
        self.selected_indices = indices

    def set_active(self, index: int) -> None:
        if index not in self.selected_indices:
            raise ValueError("activeは選出済みポケモンから選んでください。")
        self.active_index = index
        self.party[index].has_entered_battle = True

    @property
    def active(self) -> BattlePokemon:
        if self.active_index is None:
            raise ValueError("activeが未設定です。")
        return self.party[self.active_index]

    @property
    def bench(self) -> list[BattlePokemon]:
        if self.active_index is None:
            return [self.party[i] for i in self.selected_indices]
        return [self.party[i] for i in self.selected_indices if i != self.active_index]

    @property
    def not_selected(self) -> list[BattlePokemon]:
        selected = set(self.selected_indices)
        return [p for idx, p in enumerate(self.party) if idx not in selected]


@dataclass
class MoveCommand:
    move_index: int
    special_command: VZ | None = None


@dataclass
class SwitchCommand:
    switch_to_index: int


ActionCommand = MoveCommand | SwitchCommand


@dataclass
class TurnCommand:
    self_command: ActionCommand
    opponent_command: ActionCommand


@dataclass
class BattleState:
    self_team: TeamState
    opponent_team: TeamState
    turn: int = 1

    @classmethod
    def from_six_vs_six(
        cls,
        self_party: list[Pokemon],
        opponent_party: list[Pokemon],
        self_selected: list[int],
        opponent_selected: list[int],
    ) -> "BattleState":
        if len(self_party) != 6 or len(opponent_party) != 6:
            raise ValueError("6vs6のチームを渡してください。")

        self_team = TeamState(party=[BattlePokemon(p) for p in self_party])
        opponent_team = TeamState(party=[BattlePokemon(p) for p in opponent_party])

        self_team.choose_three(self_selected)
        opponent_team.choose_three(opponent_selected)

        self_team.set_active(self_selected[0])
        opponent_team.set_active(opponent_selected[0])

        return cls(self_team=self_team, opponent_team=opponent_team)


class BattleEngine:
    """6vs6(3選出)バトル進行の最小実装。"""

    def __init__(self, state: BattleState) -> None:
        self.state = state

    def resolve_turn(self, commands: TurnCommand) -> None:
        self._resolve_switch_phase(commands)
        self._resolve_transform_phase(commands)
        self._resolve_move_phase(commands)
        self.state.turn += 1

    def _resolve_switch_phase(self, commands: TurnCommand) -> None:
        actions: list[tuple[str, SwitchCommand]] = []
        if isinstance(commands.self_command, SwitchCommand):
            actions.append(("self", commands.self_command))
        if isinstance(commands.opponent_command, SwitchCommand):
            actions.append(("opponent", commands.opponent_command))

        actions.sort(
            key=lambda x: self._current_speed(is_self=(x[0] == "self")),
            reverse=True,
        )

        if len(actions) == 2 and self._current_speed(True) == self._current_speed(False):
            random.shuffle(actions)

        for side, action in actions:
            self._apply_switch(side, action.switch_to_index)

    def _resolve_transform_phase(self, commands: TurnCommand) -> None:
        ordered = self._order_by_speed([("self", commands.self_command), ("opponent", commands.opponent_command)])
        for side, action in ordered:
            if isinstance(action, MoveCommand) and action.special_command is not None:
                self._apply_special_command(side, action.special_command)

    def _resolve_move_phase(self, commands: TurnCommand) -> None:
        actions: list[tuple[str, MoveCommand, Move]] = []

        if isinstance(commands.self_command, MoveCommand):
            move = self._active(side="self").source.moves[commands.self_command.move_index]
            actions.append(("self", commands.self_command, move))

        if isinstance(commands.opponent_command, MoveCommand):
            move = self._active(side="opponent").source.moves[commands.opponent_command.move_index]
            actions.append(("opponent", commands.opponent_command, move))

        actions.sort(
            key=lambda x: (
                x[2].priority.value if isinstance(x[2].priority, Priority) else 0,
                self._current_speed(is_self=(x[0] == "self")),
            ),
            reverse=True,
        )

        if (
            len(actions) == 2
            and actions[0][2].priority.value == actions[1][2].priority.value
            and self._current_speed(True) == self._current_speed(False)
        ):
            random.shuffle(actions)

        for side, _, move in actions:
            self._activate_move(side=side, move=move)

    def _activate_move(self, side: str, move: Move) -> None:
        attacker = self._active(side=side)
        defender = self._active(side="opponent" if side == "self" else "self")

        if attacker.fainted or defender.fainted:
            return

        defender.receive_damage(move.damage)

        if move.effect is not None:
            move.effect.property.apply(attacker=attacker, defender=defender, move=move)

    def _apply_special_command(self, side: str, command: VZ) -> None:
        actor = self._active(side=side)
        if command.is_transform != 1:
            return

        if isinstance(command, MegaEvolution) and actor.source.mega_evolution_target is not None:
            actor.source = actor.source.mega_evolution_target
            if actor.source.real_stats is None:
                actor.source.calculate_and_assign_real_stats()

    def _apply_switch(self, side: str, switch_to_index: int) -> None:
        team = self.state.self_team if side == "self" else self.state.opponent_team
        team.set_active(switch_to_index)

    def _active(self, side: str) -> BattlePokemon:
        return self.state.self_team.active if side == "self" else self.state.opponent_team.active

    def _current_speed(self, is_self: bool) -> int:
        return self.state.self_team.active.speed if is_self else self.state.opponent_team.active.speed

    def _order_by_speed(self, pairs: list[tuple[str, ActionCommand]]) -> list[tuple[str, ActionCommand]]:
        ordered = sorted(pairs, key=lambda x: self._current_speed(is_self=(x[0] == "self")), reverse=True)
        if len(ordered) == 2 and self._current_speed(True) == self._current_speed(False):
            random.shuffle(ordered)
        return ordered
