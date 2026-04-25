from __future__ import annotations

from dataclasses import dataclass, field
from math import floor
from pathlib import Path
import json
from typing import Iterable


STAT_DIMENSION = 6
CHAMPIONS_EV_TO_CLASSIC_EV = 8


STAT_INDEX = {
    "hp": 0,
    "attack": 1,
    "defense": 2,
    "special_attack": 3,
    "special_defense": 4,
    "speed": 5,
}


def _nature_modifier(increase: int | None, decrease: int | None) -> StatVector:
    values = [1.0] * STAT_DIMENSION
    if increase is not None:
        values[increase] = 1.1
    if decrease is not None:
        values[decrease] = 0.9
    return StatVector(tuple(values))


@dataclass(frozen=True)
class StatVector:
    """6次元ステータスベクトル。"""

    values: tuple[float, float, float, float, float, float]

    def __post_init__(self) -> None:
        if len(self.values) != STAT_DIMENSION:
            raise ValueError(f"ステータスベクトルは{STAT_DIMENSION}次元である必要があります。")

    def as_int_tuple(self) -> tuple[int, int, int, int, int, int]:
        return tuple(int(v) for v in self.values)  # type: ignore[return-value]


@dataclass(frozen=True)
class Nature:
    """性格クラス。補正値ベクトルは6次元（HPは通常1.0固定想定）。"""

    name: str
    modifier: StatVector

    def __post_init__(self) -> None:
        mods = self.modifier.values
        allowed = {0.9, 1.0, 1.1}
        if any(m not in allowed for m in mods):
            raise ValueError("性格補正値は 0.9 / 1.0 / 1.1 のみ使用可能です。")

        count_09 = sum(1 for m in mods if m == 0.9)
        count_11 = sum(1 for m in mods if m == 1.1)
        count_10 = sum(1 for m in mods if m == 1.0)

        valid_neutral = count_10 == STAT_DIMENSION
        valid_boost_drop = count_09 == 1 and count_11 == 1 and count_10 == STAT_DIMENSION - 2

        if not (valid_neutral or valid_boost_drop):
            raise ValueError("性格補正ベクトルは、全て1.0 または 0.9/1.1を1つずつ含む形式のみ有効です。")


@dataclass
class EffectProperty:
    """効果の性質クラス（詳細ロジックは今後実装）。"""

    name: str

    def apply(self, *args, **kwargs) -> None:
        pass


@dataclass
class EffectChance:
    """効果確率クラス。"""

    property: EffectProperty
    activation_probability: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.activation_probability <= 1.0:
            raise ValueError("発動確率は0.0〜1.0で指定してください。")


@dataclass
class StatusCondition(EffectProperty):
    """状態異常クラス（毒・麻痺・凍り等）。"""

    def on_turn_start(self, *args, **kwargs) -> None:
        pass


@dataclass
class StateChange(EffectProperty):
    """状態変化クラス（混乱・メロメロ等）。"""

    def on_turn_start(self, *args, **kwargs) -> None:
        pass


@dataclass
class Paralysis(StatusCondition):
    name: str = "麻痺"


@dataclass
class Freeze(StatusCondition):
    name: str = "凍り"


@dataclass
class Burn(StatusCondition):
    name: str = "火傷"


@dataclass
class Confusion(StateChange):
    name: str = "混乱"


@dataclass
class Infatuation(StateChange):
    name: str = "メロメロ"


@dataclass(frozen=True)
class Priority:
    """技優先度クラス。"""

    value: int = 0


@dataclass
class VZ:
    """特殊コマンド基底クラス。"""

    name: str
    is_transform: int = 0

    def activate(self, pokemon: "Pokemon") -> None:
        pass


@dataclass
class MegaEvolution(VZ):
    """メガシンカ。"""

    name: str = "メガシンカ"
    is_transform: int = 1


@dataclass
class Move:
    """技クラス。"""

    name: str
    damage: int
    accuracy: float
    priority: Priority = field(default_factory=Priority)
    effect: EffectChance | None = None

    def __post_init__(self) -> None:
        if self.damage < 0:
            raise ValueError("ダメージは0以上の整数である必要があります。")
        if not 0.0 <= self.accuracy <= 1.0:
            raise ValueError("命中率は0.0〜1.0で指定してください。")

    def execute(self, *args, **kwargs) -> None:
        pass


@dataclass
class Ability:
    """特性クラス。"""

    name: str
    effect: EffectChance | None = None

    def trigger(self, *args, **kwargs) -> None:
        pass


@dataclass
class Pokemon:
    """ポケモンクラス。"""

    name: str
    base_stats: StatVector
    nature: Nature
    real_stats: StatVector | None = None
    effort_values: StatVector = field(default_factory=lambda: StatVector((0, 0, 0, 0, 0, 0)))
    moves: list[Move] = field(default_factory=list)
    ability: Ability | None = None
    level: int = 50
    individual_values: StatVector = field(default_factory=lambda: StatVector((31, 31, 31, 31, 31, 31)))
    champions_ev_scaling: bool = True
    mega_evolution_target: "Pokemon | None" = None
    stat_stages: list[int] = field(default_factory=lambda: [0] * STAT_DIMENSION)
    status_condition: StatusCondition | None = None
    state_changes: list[StateChange] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.stat_stages) != STAT_DIMENSION:
            raise ValueError(f"ステータス変化段階は{STAT_DIMENSION}次元である必要があります。")
        if any(stage < -6 or stage > 6 for stage in self.stat_stages):
            raise ValueError("ステータス変化段階は-6〜6で指定してください。")

    @classmethod
    def load_from_dataset(
        cls,
        loader: "DatasetLoader",
        pokemon_name: str,
        nature_name: str,
    ) -> "Pokemon":
        """データセットからポケモンを生成する。"""
        base_stats = loader.load_base_stats(pokemon_name)
        nature = loader.load_nature(nature_name)
        return cls(name=pokemon_name, base_stats=base_stats, nature=nature)

    def set_effort_values(self, ev_vector: StatVector) -> None:
        """努力値ベクトルを設定する（合計66制約）。"""
        ev_int = ev_vector.as_int_tuple()
        if any(v < 0 for v in ev_int):
            raise ValueError("努力値に負の値は設定できません。")
        if sum(ev_int) != 66:
            raise ValueError("努力値ベクトルの合計は66である必要があります。")
        self.effort_values = StatVector(tuple(ev_int))

    def calculate_and_assign_real_stats(self) -> None:
        """種族値・努力値・性格（+個体値/レベル）から実数値を計算し割り当てる。"""
        base = self.base_stats.as_int_tuple()
        ev = self.effort_values.as_int_tuple()
        iv = self.individual_values.as_int_tuple()
        nature = self.nature.modifier.values

        calculated: list[int] = []
        for i in range(STAT_DIMENSION):
            effective_ev = ev[i] * CHAMPIONS_EV_TO_CLASSIC_EV if self.champions_ev_scaling else ev[i]
            common = floor(((2 * base[i] + iv[i] + floor(effective_ev / 4)) * self.level) / 100)
            if i == 0:  # HP
                stat = common + self.level + 10
            else:
                stat = floor((common + 5) * nature[i])
            calculated.append(int(stat))

        self.real_stats = StatVector(tuple(calculated))

    def set_mega_evolution_target(self, target: "Pokemon") -> None:
        self.mega_evolution_target = target

    def set_stat_stage(self, stat_index: int, stage: int) -> None:
        if not 0 <= stat_index < STAT_DIMENSION:
            raise IndexError("stat_indexが不正です。")
        self.stat_stages[stat_index] = max(-6, min(6, int(stage)))

    def apply_stat_stage_delta(self, stat_index: int, delta: int) -> None:
        if not 0 <= stat_index < STAT_DIMENSION:
            raise IndexError("stat_indexが不正です。")
        self.set_stat_stage(stat_index, self.stat_stages[stat_index] + delta)

    def try_set_status_condition(self, condition: StatusCondition) -> bool:
        """状態異常が未設定なら付与し、既にある場合は失敗する。"""
        if self.status_condition is not None:
            return False
        self.status_condition = condition
        return True

    def add_state_change(self, state_change: StateChange) -> None:
        """状態変化を追加する（状態異常とは独立して重複可能）。"""
        self.state_changes.append(state_change)


class DatasetLoader:
    """データセットローダー。JSONを前提に最小実装。"""

    def __init__(self, dataset_dir: str | Path) -> None:
        self.dataset_dir = Path(dataset_dir)

    def _load_json(self, filename: str) -> dict:
        file_path = self.dataset_dir / filename
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def load_base_stats(self, pokemon_name: str) -> StatVector:
        species_data = self._load_json("species.json")
        values = species_data[pokemon_name]["base_stats"]
        return StatVector(tuple(values))

    def load_nature(self, nature_name: str) -> Nature:
        try:
            nature_data = self._load_json("natures.json")
            entry = nature_data[nature_name]
            return Nature(name=nature_name, modifier=StatVector(tuple(entry["modifier"])))
        except (FileNotFoundError, KeyError):
            standard = {nature.name: nature for nature in create_standard_natures()}
            if nature_name not in standard:
                raise KeyError(f"未定義の性格です: {nature_name}")
            return standard[nature_name]

    def load_moves_for_pokemon(self, pokemon_name: str) -> list[Move]:
        pass

    def load_ability_for_pokemon(self, pokemon_name: str) -> Ability:
        pass

    def load_effect_property(self, effect_name: str) -> EffectProperty:
        pass


def create_standard_natures() -> list[Nature]:
    """25種類の性格を標準定義として返す。"""

    atk = STAT_INDEX["attack"]
    deff = STAT_INDEX["defense"]
    spa = STAT_INDEX["special_attack"]
    spd = STAT_INDEX["special_defense"]
    spe = STAT_INDEX["speed"]

    return [
        Nature(name="がんばりや", modifier=_nature_modifier(None, None)),
        Nature(name="さみしがり", modifier=_nature_modifier(atk, deff)),
        Nature(name="ゆうかん", modifier=_nature_modifier(atk, spe)),
        Nature(name="いじっぱり", modifier=_nature_modifier(atk, spa)),
        Nature(name="やんちゃ", modifier=_nature_modifier(atk, spd)),
        Nature(name="ずぶとい", modifier=_nature_modifier(deff, atk)),
        Nature(name="すなお", modifier=_nature_modifier(None, None)),
        Nature(name="のんき", modifier=_nature_modifier(deff, spe)),
        Nature(name="わんぱく", modifier=_nature_modifier(deff, spa)),
        Nature(name="のうてんき", modifier=_nature_modifier(deff, spd)),
        Nature(name="ひかえめ", modifier=_nature_modifier(spa, atk)),
        Nature(name="おっとり", modifier=_nature_modifier(spa, deff)),
        Nature(name="れいせい", modifier=_nature_modifier(spa, spe)),
        Nature(name="てれや", modifier=_nature_modifier(None, None)),
        Nature(name="うっかりや", modifier=_nature_modifier(spa, spd)),
        Nature(name="おだやか", modifier=_nature_modifier(spd, atk)),
        Nature(name="おとなしい", modifier=_nature_modifier(spd, deff)),
        Nature(name="なまいき", modifier=_nature_modifier(spd, spe)),
        Nature(name="しんちょう", modifier=_nature_modifier(spd, spa)),
        Nature(name="きまぐれ", modifier=_nature_modifier(None, None)),
        Nature(name="おくびょう", modifier=_nature_modifier(spe, atk)),
        Nature(name="せっかち", modifier=_nature_modifier(spe, deff)),
        Nature(name="ようき", modifier=_nature_modifier(spe, spa)),
        Nature(name="むじゃき", modifier=_nature_modifier(spe, spd)),
        Nature(name="まじめ", modifier=_nature_modifier(None, None)),
    ]


def validate_stat_vector(values: Iterable[int | float]) -> StatVector:
    """外部入力用のバリデーション付き変換。"""

    raw = tuple(values)
    if len(raw) != STAT_DIMENSION:
        raise ValueError(f"ベクトル長は{STAT_DIMENSION}が必要です。")
    return StatVector(tuple(raw))
