from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .models import Match, MatchResult, Player, Round, Stage


WIN_POINTS = 1.0
DRAW_POINTS = 0.5
LOSS_POINTS = 0.0
BYE_POINTS = 1.0


@dataclass
class Standing:
    player: Player
    points: float = 0.0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    byes: int = 0
    opponents: list[Player] = field(default_factory=list)
    had_bye: bool = False

    @property
    def games_played(self) -> int:
        return self.wins + self.losses + self.draws

    def opponent_match_win_rate(self, table: dict[str, "Standing"]) -> float:
        if not self.opponents:
            return 0.0
        rates = []
        for opp in self.opponents:
            s = table[opp.id]
            played = s.games_played
            if played == 0:
                rates.append(0.0)
            else:
                rates.append(s.points / played)
        return sum(rates) / len(rates)


class SwissStage:
    """Swiss-system stage with N rounds, supporting odd-count byes."""

    def __init__(
        self,
        players: list[Player],
        rounds: int = 3,
        name: str = "Swiss",
        advance: Optional[int] = None,
    ) -> None:
        if rounds < 1:
            raise ValueError("Swiss stage needs at least one round")
        if len(players) < 2:
            raise ValueError("Swiss stage needs at least two players")
        self.players = list(players)
        self.num_rounds = rounds
        self.name = name
        self.advance = advance
        self.stage = Stage(name=name)
        self.standings: dict[str, Standing] = {
            p.id: Standing(player=p) for p in self.players
        }

    def build_stage(self) -> Stage:
        return self.stage

    def pair_next_round(self) -> Round:
        if len(self.stage.rounds) >= self.num_rounds:
            raise RuntimeError("All Swiss rounds already paired")
        if self.stage.rounds and not self.stage.rounds[-1].complete:
            raise RuntimeError("Previous round must be reported before pairing")

        round_number = len(self.stage.rounds) + 1
        if round_number == 1:
            pairs, bye_player = self._pair_first_round()
        else:
            pairs, bye_player = self._pair_subsequent_round()

        matches: list[Match] = []
        for idx, (a, b) in enumerate(pairs, start=1):
            matches.append(
                Match(
                    id=f"{self.name}-R{round_number}-M{idx}",
                    round_number=round_number,
                    p1=a,
                    p2=b,
                    bracket="swiss",
                )
            )
        if bye_player is not None:
            bye_match = Match(
                id=f"{self.name}-R{round_number}-BYE",
                round_number=round_number,
                p1=bye_player,
                p2=None,
                result=MatchResult.BYE,
                bracket="swiss",
            )
            matches.append(bye_match)
            self._apply_bye(bye_player)

        rd = Round(number=round_number, matches=matches, label=f"Swiss Round {round_number}")
        self.stage.rounds.append(rd)
        return rd

    def report_match(self, match: Match, result: MatchResult) -> None:
        match.report(result)
        if match.result == MatchResult.BYE:
            return
        s1 = self.standings[match.p1.id]
        s2 = self.standings[match.p2.id]
        s1.opponents.append(match.p2)
        s2.opponents.append(match.p1)
        if result == MatchResult.P1_WIN:
            s1.points += WIN_POINTS
            s1.wins += 1
            s2.losses += 1
        elif result == MatchResult.P2_WIN:
            s2.points += WIN_POINTS
            s2.wins += 1
            s1.losses += 1
        elif result == MatchResult.DRAW:
            s1.points += DRAW_POINTS
            s2.points += DRAW_POINTS
            s1.draws += 1
            s2.draws += 1
        else:
            raise ValueError(f"Unexpected result for swiss match: {result}")

    def ranked_standings(self) -> list[Standing]:
        rows = list(self.standings.values())
        rows.sort(
            key=lambda s: (
                -s.points,
                -s.opponent_match_win_rate(self.standings),
                s.player.seed if s.player.seed else 9999,
                s.player.name.lower(),
            )
        )
        return rows

    def qualifiers(self) -> list[Player]:
        ranked = [s.player for s in self.ranked_standings()]
        if self.advance is None:
            return ranked
        return ranked[: self.advance]

    def _pair_first_round(self) -> tuple[list[tuple[Player, Player]], Optional[Player]]:
        seeded = sorted(self.players, key=lambda p: (p.seed if p.seed else 9999, p.name.lower()))
        bye_player: Optional[Player] = None
        if len(seeded) % 2 == 1:
            bye_player = seeded[-1]
            seeded = seeded[:-1]
        half = len(seeded) // 2
        top, bot = seeded[:half], seeded[half:]
        return list(zip(top, bot)), bye_player

    def _pair_subsequent_round(self) -> tuple[list[tuple[Player, Player]], Optional[Player]]:
        ranked = self.ranked_standings()
        bye_player: Optional[Player] = None
        if len(ranked) % 2 == 1:
            bye_player = self._pick_bye(ranked)
            ranked = [s for s in ranked if s.player.id != bye_player.id]

        groups: dict[float, list[Standing]] = defaultdict(list)
        for s in ranked:
            groups[s.points].append(s)
        score_keys = sorted(groups.keys(), reverse=True)
        ordered = [s for k in score_keys for s in groups[k]]

        pairs = self._pair_with_backtrack(ordered)
        if pairs is None:
            pairs = self._fallback_pair(ordered)
        return [(a.player, b.player) for a, b in pairs], bye_player

    def _pick_bye(self, ranked: list[Standing]) -> Player:
        for s in reversed(ranked):
            if not s.had_bye:
                return s.player
        return ranked[-1].player

    def _pair_with_backtrack(
        self, ordered: list[Standing]
    ) -> Optional[list[tuple[Standing, Standing]]]:
        played: set[frozenset[str]] = set()
        for s in ordered:
            for opp in s.opponents:
                played.add(frozenset({s.player.id, opp.id}))

        result: list[tuple[Standing, Standing]] = []

        def backtrack(remaining: list[Standing]) -> bool:
            if not remaining:
                return True
            head = remaining[0]
            for i in range(1, len(remaining)):
                cand = remaining[i]
                if frozenset({head.player.id, cand.player.id}) in played:
                    continue
                result.append((head, cand))
                next_remaining = remaining[1:i] + remaining[i + 1 :]
                if backtrack(next_remaining):
                    return True
                result.pop()
            return False

        if backtrack(ordered):
            return result
        return None

    def _fallback_pair(self, ordered: list[Standing]) -> list[tuple[Standing, Standing]]:
        pairs: list[tuple[Standing, Standing]] = []
        i = 0
        while i < len(ordered):
            pairs.append((ordered[i], ordered[i + 1]))
            i += 2
        return pairs

    def _apply_bye(self, player: Player) -> None:
        s = self.standings[player.id]
        s.points += BYE_POINTS
        s.byes += 1
        s.had_bye = True
