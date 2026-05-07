from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


BYE = "BYE"


class MatchResult(str, Enum):
    PENDING = "pending"
    P1_WIN = "p1_win"
    P2_WIN = "p2_win"
    DRAW = "draw"
    BYE = "bye"


@dataclass
class Player:
    id: str
    name: str
    seed: int = 0

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Player) and self.id == other.id


@dataclass
class Match:
    id: str
    round_number: int
    p1: Optional[Player]
    p2: Optional[Player]
    result: MatchResult = MatchResult.PENDING
    bracket: str = ""

    @property
    def is_bye(self) -> bool:
        return self.p1 is None or self.p2 is None

    @property
    def winner(self) -> Optional[Player]:
        if self.result == MatchResult.BYE:
            return self.p1 or self.p2
        if self.result == MatchResult.P1_WIN:
            return self.p1
        if self.result == MatchResult.P2_WIN:
            return self.p2
        return None

    @property
    def loser(self) -> Optional[Player]:
        if self.result == MatchResult.BYE:
            return None
        if self.result == MatchResult.P1_WIN:
            return self.p2
        if self.result == MatchResult.P2_WIN:
            return self.p1
        return None

    def report(self, result: MatchResult) -> None:
        if self.is_bye and result != MatchResult.BYE:
            raise ValueError("bye matches must be reported as BYE")
        if not self.is_bye and result == MatchResult.BYE:
            raise ValueError("non-bye matches cannot be reported as BYE")
        self.result = result


@dataclass
class Round:
    number: int
    matches: list[Match] = field(default_factory=list)
    label: str = ""

    @property
    def complete(self) -> bool:
        return all(m.result != MatchResult.PENDING for m in self.matches)


@dataclass
class Stage:
    name: str
    rounds: list[Round] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.rounds) and all(r.complete for r in self.rounds)


@dataclass
class Tournament:
    name: str
    players: list[Player]
    stages: list[Stage] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.stages) and all(s.complete for s in self.stages)
