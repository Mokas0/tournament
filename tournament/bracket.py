from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Match, MatchResult, Player, Round, Stage


def next_power_of_two(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def standard_seed_order(size: int) -> list[int]:
    """Return seed positions for a single-elim bracket of `size` slots.

    Pairs 1 vs size, 2 vs size-1, etc., recursively so that top seeds meet
    in the final. Result is a list of seed numbers in slot order.
    """
    if size < 1 or size & (size - 1) != 0:
        raise ValueError("size must be a power of two")
    order = [1, 2]
    while len(order) < size:
        new_order: list[int] = []
        n = len(order) * 2
        for s in order:
            new_order.append(s)
            new_order.append(n + 1 - s)
        order = new_order
    return order


@dataclass
class _Slot:
    player: Optional[Player]
    is_bye: bool = False


class DoubleEliminationStage:
    """Double-elimination bracket with byes for non-power-of-two fields.

    Players are seeded into a winners bracket sized to the next power of two;
    extra slots are byes that auto-advance their opponent. Losers drop into
    the losers bracket. The grand final pairs the winners-bracket champion
    against the losers-bracket champion (with a reset match if the LB winner
    wins the first grand final).
    """

    def __init__(
        self,
        players: list[Player],
        name: str = "Bracket",
        grand_final_reset: bool = True,
    ) -> None:
        if len(players) < 2:
            raise ValueError("Bracket needs at least two players")
        self.players = list(players)
        self.name = name
        self.grand_final_reset = grand_final_reset
        self.stage = Stage(name=name)

        self.bracket_size = next_power_of_two(len(players))
        self.wb_rounds: list[list[Match]] = []
        self.lb_rounds: list[list[Match]] = []
        self.gf_match: Optional[Match] = None
        self.gf_reset_match: Optional[Match] = None

        self._match_counter = 0
        self._build()

    def build_stage(self) -> Stage:
        return self.stage

    def report_match(self, match: Match, result: MatchResult) -> None:
        match.report(result)
        self._propagate(match)

    def champion(self) -> Optional[Player]:
        if self.gf_reset_match and self.gf_reset_match.result not in (
            MatchResult.PENDING,
        ):
            return self.gf_reset_match.winner
        if self.gf_match and self.gf_match.result not in (MatchResult.PENDING,):
            wb_winner = self._wb_final_winner()
            if self.gf_match.winner == wb_winner:
                return wb_winner
            if not self.grand_final_reset:
                return self.gf_match.winner
            return None
        return None

    def _new_match_id(self, label: str) -> str:
        self._match_counter += 1
        return f"{self.name}-{label}-{self._match_counter}"

    def _build(self) -> None:
        slots = self._seed_slots()
        self._build_winners(slots)
        self._build_losers()
        self._build_grand_final()
        self._collect_rounds()
        self._auto_advance_byes()

    def _seed_slots(self) -> list[_Slot]:
        size = self.bracket_size
        order = standard_seed_order(size)
        seeded = sorted(
            self.players,
            key=lambda p: (p.seed if p.seed else 9999, p.name.lower()),
        )
        slots: list[_Slot] = []
        for seed_pos in order:
            idx = seed_pos - 1
            if idx < len(seeded):
                slots.append(_Slot(player=seeded[idx]))
            else:
                slots.append(_Slot(player=None, is_bye=True))
        return slots

    def _build_winners(self, slots: list[_Slot]) -> None:
        round_matches: list[Match] = []
        for i in range(0, len(slots), 2):
            a, b = slots[i], slots[i + 1]
            if a.is_bye and b.is_bye:
                p1, p2, result = None, None, MatchResult.BYE
            elif a.is_bye:
                p1, p2, result = b.player, None, MatchResult.BYE
            elif b.is_bye:
                p1, p2, result = a.player, None, MatchResult.BYE
            else:
                p1, p2, result = a.player, b.player, MatchResult.PENDING
            m = Match(
                id=self._new_match_id("WB-R1"),
                round_number=1,
                p1=p1,
                p2=p2,
                result=result,
                bracket="winners",
            )
            round_matches.append(m)
        self.wb_rounds.append(round_matches)

        round_num = 2
        prev = round_matches
        while len(prev) > 1:
            nxt: list[Match] = []
            for _ in range(len(prev) // 2):
                m = Match(
                    id=self._new_match_id(f"WB-R{round_num}"),
                    round_number=round_num,
                    p1=None,
                    p2=None,
                    bracket="winners",
                )
                nxt.append(m)
            self.wb_rounds.append(nxt)
            prev = nxt
            round_num += 1

    def _build_losers(self) -> None:
        wb1_size = len(self.wb_rounds[0])
        if wb1_size < 2:
            return

        lb_round_num = 1
        first = []
        for _ in range(wb1_size // 2):
            first.append(
                Match(
                    id=self._new_match_id(f"LB-R{lb_round_num}"),
                    round_number=lb_round_num,
                    p1=None,
                    p2=None,
                    bracket="losers",
                )
            )
        self.lb_rounds.append(first)

        wb_round_idx = 1
        prev_lb_size = len(first)
        while prev_lb_size > 1 or wb_round_idx < len(self.wb_rounds):
            lb_round_num += 1
            consolidation = []
            for _ in range(prev_lb_size):
                consolidation.append(
                    Match(
                        id=self._new_match_id(f"LB-R{lb_round_num}"),
                        round_number=lb_round_num,
                        p1=None,
                        p2=None,
                        bracket="losers",
                    )
                )
            self.lb_rounds.append(consolidation)
            wb_round_idx += 1

            if len(consolidation) > 1:
                lb_round_num += 1
                merge_size = len(consolidation) // 2
                merge = []
                for _ in range(merge_size):
                    merge.append(
                        Match(
                            id=self._new_match_id(f"LB-R{lb_round_num}"),
                            round_number=lb_round_num,
                            p1=None,
                            p2=None,
                            bracket="losers",
                        )
                    )
                self.lb_rounds.append(merge)
                prev_lb_size = merge_size
            else:
                prev_lb_size = 1
                break

    def _build_grand_final(self) -> None:
        self.gf_match = Match(
            id=self._new_match_id("GF"),
            round_number=1,
            p1=None,
            p2=None,
            bracket="grand_final",
        )
        if self.grand_final_reset:
            self.gf_reset_match = Match(
                id=self._new_match_id("GF-RESET"),
                round_number=2,
                p1=None,
                p2=None,
                bracket="grand_final",
            )

    def _collect_rounds(self) -> None:
        rounds: list[Round] = []
        round_no = 0
        for i, matches in enumerate(self.wb_rounds, start=1):
            round_no += 1
            rounds.append(Round(number=round_no, matches=list(matches), label=f"Winners R{i}"))
        for i, matches in enumerate(self.lb_rounds, start=1):
            round_no += 1
            rounds.append(Round(number=round_no, matches=list(matches), label=f"Losers R{i}"))
        if self.gf_match:
            round_no += 1
            rounds.append(Round(number=round_no, matches=[self.gf_match], label="Grand Final"))
        if self.gf_reset_match:
            round_no += 1
            rounds.append(
                Round(number=round_no, matches=[self.gf_reset_match], label="Grand Final Reset")
            )
        self.stage.rounds = rounds

    def _auto_advance_byes(self) -> None:
        for m in self.wb_rounds[0]:
            if m.result == MatchResult.BYE:
                self._propagate(m)

    def _propagate(self, match: Match) -> None:
        if match.bracket == "winners":
            self._propagate_winners(match)
        elif match.bracket == "losers":
            self._propagate_losers(match)
        elif match.bracket == "grand_final":
            self._propagate_grand_final(match)

    def _propagate_winners(self, match: Match) -> None:
        round_idx = self._wb_round_index(match)
        match_idx = self.wb_rounds[round_idx].index(match)
        winner = match.winner
        loser = match.loser

        if round_idx + 1 < len(self.wb_rounds):
            nxt = self.wb_rounds[round_idx + 1][match_idx // 2]
            self._place(nxt, winner)
        else:
            self._place(self.gf_match, winner)

        if loser is not None and self.lb_rounds:
            self._drop_to_losers(round_idx, match_idx, loser)
        elif loser is None and round_idx == 0 and self.lb_rounds:
            self._drop_to_losers(round_idx, match_idx, None)

    def _drop_to_losers(self, wb_round_idx: int, wb_match_idx: int, loser: Optional[Player]) -> None:
        if wb_round_idx == 0:
            target = self.lb_rounds[0][wb_match_idx // 2]
            self._place(target, loser)
            self._maybe_auto_bye(target)
            return

        consolidation_idx = wb_round_idx * 2 - 1
        if consolidation_idx >= len(self.lb_rounds):
            return
        target = self.lb_rounds[consolidation_idx][wb_match_idx]
        self._place(target, loser)
        self._maybe_auto_bye(target)

    def _propagate_losers(self, match: Match) -> None:
        round_idx = self._lb_round_index(match)
        match_idx = self.lb_rounds[round_idx].index(match)
        winner = match.winner

        if round_idx + 1 < len(self.lb_rounds):
            nxt_round = self.lb_rounds[round_idx + 1]
            is_consolidation_next = (round_idx % 2 == 0)
            if is_consolidation_next:
                target = nxt_round[match_idx]
            else:
                target = nxt_round[match_idx // 2]
            self._place(target, winner)
            self._maybe_auto_bye(target)
        else:
            self._place(self.gf_match, winner)

    def _propagate_grand_final(self, match: Match) -> None:
        if match is self.gf_match and self.gf_reset_match:
            wb_winner = self._wb_final_winner()
            if match.winner != wb_winner:
                self.gf_reset_match.p1 = match.p1
                self.gf_reset_match.p2 = match.p2

    def _maybe_auto_bye(self, match: Match) -> None:
        if match.result != MatchResult.PENDING:
            return
        if match.p1 is None and match.p2 is None:
            return
        if match.p1 is None or match.p2 is None:
            match.result = MatchResult.BYE
            self._propagate(match)

    def _place(self, match: Optional[Match], player: Optional[Player]) -> None:
        if match is None:
            return
        if match.p1 is None:
            match.p1 = player
        elif match.p2 is None:
            match.p2 = player

    def _wb_round_index(self, match: Match) -> int:
        for i, rnd in enumerate(self.wb_rounds):
            if match in rnd:
                return i
        raise ValueError("match not in winners bracket")

    def _lb_round_index(self, match: Match) -> int:
        for i, rnd in enumerate(self.lb_rounds):
            if match in rnd:
                return i
        raise ValueError("match not in losers bracket")

    def _wb_final_winner(self) -> Optional[Player]:
        if not self.wb_rounds:
            return None
        final = self.wb_rounds[-1]
        if not final:
            return None
        return final[-1].winner
