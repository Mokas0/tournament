from __future__ import annotations

from typing import Optional

from .bracket import DoubleEliminationStage
from .models import Match, MatchResult, Player, Tournament
from .swiss import SwissStage


class TournamentRunner:
    """Orchestrates a Swiss group stage followed by a double-elim playoff.

    Lifecycle:
        runner = TournamentRunner(name, players, swiss_rounds=3, advance=8)
        rd = runner.next_swiss_round()
        runner.report(match, MatchResult.P1_WIN)
        ...
        runner.start_bracket()  # call once Swiss is complete
        runner.report(match, MatchResult.P2_WIN)
        runner.champion()
    """

    def __init__(
        self,
        name: str,
        players: list[Player],
        swiss_rounds: int = 3,
        advance: Optional[int] = None,
        grand_final_reset: bool = True,
    ) -> None:
        if len(players) < 2:
            raise ValueError("Tournament needs at least two players")
        if advance is not None and (advance < 2 or advance > len(players)):
            raise ValueError("`advance` must be between 2 and the player count")
        self.name = name
        self.advance = advance if advance is not None else len(players)
        self.grand_final_reset = grand_final_reset

        self.swiss = SwissStage(
            players=players,
            rounds=swiss_rounds,
            name=f"{name} - Swiss",
            advance=self.advance,
        )
        self.bracket: Optional[DoubleEliminationStage] = None
        self.tournament = Tournament(name=name, players=list(players))
        self.tournament.stages.append(self.swiss.build_stage())

    def next_swiss_round(self):
        return self.swiss.pair_next_round()

    def report(self, match: Match, result: MatchResult) -> None:
        if match.bracket == "swiss":
            self.swiss.report_match(match, result)
            return
        if self.bracket is None:
            raise RuntimeError("Bracket not started yet")
        self.bracket.report_match(match, result)

    def swiss_complete(self) -> bool:
        return self.swiss.stage.complete and len(self.swiss.stage.rounds) == self.swiss.num_rounds

    def start_bracket(self) -> DoubleEliminationStage:
        if self.bracket is not None:
            return self.bracket
        if not self.swiss_complete():
            raise RuntimeError("Cannot start bracket until Swiss is complete")
        qualifiers = self.swiss.qualifiers()
        seeded = [
            Player(id=p.id, name=p.name, seed=i + 1)
            for i, p in enumerate(qualifiers)
        ]
        self.bracket = DoubleEliminationStage(
            players=seeded,
            name=f"{self.name} - Playoffs",
            grand_final_reset=self.grand_final_reset,
        )
        self.tournament.stages.append(self.bracket.build_stage())
        return self.bracket

    def champion(self) -> Optional[Player]:
        if self.bracket is None:
            return None
        return self.bracket.champion()

    def standings(self):
        return self.swiss.ranked_standings()
