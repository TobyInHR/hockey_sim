import random
from typing import Dict, List, Optional

from .config import SimConfig
from .engine import simulate_game_once
from .models import SeriesResult, Team


def run_series(cfg: SimConfig, home: Team, away: Team, games: int, seed: Optional[int] = None) -> SeriesResult:
    games = max(1, min(cfg.max_games, int(games)))
    rng = random.Random(seed)

    home_wins = away_wins = ties = 0

    # aggregates for report-friendly stats
    agg = {
        home.name: {"Goals": 0, "xG": 0.0, "SOG": 0, "Att": 0, "GV": 0, "TK": 0, "HIT": 0, "PPG": 0, "PPO": 0},
        away.name: {"Goals": 0, "xG": 0.0, "SOG": 0, "Att": 0, "GV": 0, "TK": 0, "HIT": 0, "PPG": 0, "PPO": 0},
    }

    results = []

    for _ in range(games):
        gr = simulate_game_once(cfg, rng, home, away)
        results.append(gr)

        if gr.home_goals > gr.away_goals:
            home_wins += 1
        elif gr.away_goals > gr.home_goals:
            away_wins += 1
        else:
            ties += 1

        # aggregate from team_summary
        for t in (home.name, away.name):
            s = gr.team_summary[t]
            agg[t]["Goals"] += int(s["Goals"])
            agg[t]["xG"] += float(s["xG"])
            agg[t]["SOG"] += int(s["SOG"])
            agg[t]["Att"] += int(s["Att"])
            agg[t]["GV"] += int(s["GV"])
            agg[t]["TK"] += int(s["TK"])
            agg[t]["HIT"] += int(s["HIT"])

            # PP “x/y”
            pp = s["PP"]
            try:
                g_sc, opp = pp.split("/")
                agg[t]["PPG"] += int(g_sc)
                agg[t]["PPO"] += int(opp)
            except Exception:
                pass

    avg: Dict[str, Dict[str, float]] = {}
    for t in (home.name, away.name):
        avg[t] = {
            "Goals": agg[t]["Goals"] / games,
            "xG": agg[t]["xG"] / games,
            "SOG": agg[t]["SOG"] / games,
            "Att": agg[t]["Att"] / games,
            "GV": agg[t]["GV"] / games,
            "TK": agg[t]["TK"] / games,
            "HIT": agg[t]["HIT"] / games,
            "PP%": (0.0 if agg[t]["PPO"] <= 0 else (100.0 * agg[t]["PPG"] / agg[t]["PPO"])),
        }

    return SeriesResult(
        home=home.name,
        away=away.name,
        games=games,
        home_wins=home_wins,
        away_wins=away_wins,
        ties=ties,
        avg=avg,
        game_results=results,
    )
