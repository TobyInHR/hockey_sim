from typing import Optional

from .models import GameResult, SeriesResult


def print_game_report(gr: GameResult, include_pbp: bool = False, pbp_limit: Optional[int] = None) -> None:
    print("\n" + "=" * 120)
    print("GAME REPORT")
    print(f"{gr.away} @ {gr.home}")
    print(f"FINAL: {gr.away} {gr.away_goals} — {gr.home} {gr.home_goals}")

    # period lines
    p1 = f"P1 {gr.away_goals_by_period[0]}-{gr.home_goals_by_period[0]}"
    p2 = f"P2 {gr.away_goals_by_period[1]}-{gr.home_goals_by_period[1]}"
    p3 = f"P3 {gr.away_goals_by_period[2]}-{gr.home_goals_by_period[2]}"
    extras = []
    if gr.went_to_ot:
        extras.append("OT")
    if gr.went_to_so:
        extras.append("SO")
    extra_str = (" | " + " ".join(extras)) if extras else ""
    print(f"BY PERIOD: {p1} | {p2} | {p3}{extra_str}")

    if gr.went_to_ot and gr.ot_winner:
        print(f"OT WINNER: {gr.ot_winner}")
    if gr.went_to_so and gr.so_winner:
        print(f"SHOOTOUT WINNER: {gr.so_winner} (shootout goals not credited to skaters/goalies)")

    print("\nTEAM SUMMARY")
    for t in (gr.away, gr.home):
        s = gr.team_summary[t]
        print(
            f"{t:10}  Goals {s['Goals']:>2} | xG {s['xG']:>5} | SOG {s['SOG']:>3} | Att {s['Att']:>3} | "
            f"SB-ag {s['SB-against']:>3} | GV {s['GV']:>3} | TK {s['TK']:>3} | HIT {s['HIT']:>3} | "
            f"PP {s['PP']:>7} | FO {s['FO']:>7}"
        )

    def print_skaters(team_name: str) -> None:
        print(f"\n{team_name} SKATERS")
        header = f"{'Player':18} {'Pos':>3} {'Unit':>4} {'G':>3} {'A':>3} {'xG':>6} {'Att':>4} {'SOG':>4} {'BLK':>4} {'GV':>4} {'TK':>4} {'HIT':>4} {'PIM':>4} {'FO':>7} {'Sh':>4} {'AvgSh':>6} {'TOI':>6}"
        print(header)
        for r in gr.skaters[team_name]:
            print(
                f"{r['Player'][:18]:18} {r['Pos']:>3} {r['Unit']:>4} {r['G']:>3} {r['A']:>3} {r['xG']:>6.2f} "
                f"{r['Att']:>4} {r['SOG']:>4} {r['BLK']:>4} {r['GV']:>4} {r['TK']:>4} {r['HIT']:>4} {r['PIM']:>4} "
                f"{r['FO']:>7} {r['Shifts']:>4} {r['AvgShift']:>6} {r['TOI']:>6}"
            )

    def print_goalies(team_name: str) -> None:
        print(f"\n{team_name} GOALIES")
        header = f"{'Goalie':18} {'Role':>7} {'GA':>3} {'SA':>3} {'SV':>3} {'SV%':>6} {'REB':>4} {'COV':>4} {'Fat':>6} {'Conf':>5} {'TOI':>6}"
        print(header)
        for r in gr.goalies[team_name]:
            print(
                f"{r['Goalie'][:18]:18} {r['Role']:>7} {r['GA']:>3} {r['SA']:>3} {r['SV']:>3} {r['SV%']:>6} "
                f"{r['REB']:>4} {r['COV']:>4} {r['Fat']:>6.1f} {r['Conf']:>5.2f} {r['TOI']:>6}"
            )

    print_skaters(gr.away)
    print_goalies(gr.away)
    print_skaters(gr.home)
    print_goalies(gr.home)

    if gr.went_to_so:
        print("\nSHOOTOUT LOG")
        for a in gr.shootout_log:
            print(f"  {a.shooter_team} shooter={a.shooter} vs {a.goalie_team} goalie={a.goalie} -> {'GOAL' if a.scored else 'SAVE'}")

    if include_pbp and gr.pbp:
        print("\nPLAY-BY-PLAY")
        lines = gr.pbp if pbp_limit is None else gr.pbp[:pbp_limit]
        for line in lines:
            print(line)


def print_series_report(sr: SeriesResult, show_each_game: bool = True) -> None:
    print("\n" + "=" * 120)
    print("SERIES REPORT")
    print(f"{sr.away} @ {sr.home} | Games: {sr.games} | Results: {sr.away} {sr.away_wins} — {sr.home} {sr.home_wins}")

    print("\nAVERAGES PER GAME")
    for t in (sr.away, sr.home):
        a = sr.avg[t]
        print(
            f"{t:10}  Goals {a['Goals']:.2f} | xG {a['xG']:.2f} | SOG {a['SOG']:.2f} | Att {a['Att']:.2f} | "
            f"GV {a['GV']:.2f} | TK {a['TK']:.2f} | HIT {a['HIT']:.2f} | PP% {a['PP%']:.1f}"
        )

    if show_each_game:
        print("\nGAME-BY-GAME")
        for i, gr in enumerate(sr.game_results, start=1):
            extra = ""
            if gr.went_to_so:
                extra = f" (SO {gr.so_winner})"
            elif gr.went_to_ot and gr.ot_winner:
                extra = f" (OT {gr.ot_winner})"
            print(f"  G{i:03d}: {gr.away} {gr.away_goals} — {gr.home} {gr.home_goals}{extra}")
