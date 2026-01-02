from typing import Optional

from .config import SimConfig
from .io import build_team, list_teams_in_skaters_csv
from .report import print_game_report, print_series_report
from .series import run_series


def prompt_int(label: str, default: int, lo: int, hi: int) -> int:
    raw = input(f"{label} [{default}]: ").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return max(lo, min(hi, v))
    except Exception:
        return default


def prompt_yes_no(label: str, default: bool) -> bool:
    d = "Y" if default else "N"
    raw = input(f"{label} (Y/N) [{d}]: ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def prompt_team_choice(teams, label: str, default_idx: int = 0) -> str:
    if not teams:
        raise ValueError("No teams found in skaters CSV.")
    print(f"\n{label}")
    for i, t in enumerate(teams, start=1):
        print(f"  {i}) {t}")
    idx = prompt_int("Choose", default_idx + 1, 1, len(teams))
    return teams[idx - 1]


def main():
    cfg = SimConfig()

    teams = list_teams_in_skaters_csv(cfg.skaters_csv_path)
    if not teams:
        print("No teams found. Check your skaters CSV path and the 'team' column.")
        return

    print("Hockey Sim (Terminal Menu)")
    away_name = prompt_team_choice(teams, "Select AWAY team", default_idx=0)
    home_name = prompt_team_choice(teams, "Select HOME team", default_idx=1 if len(teams) > 1 else 0)

    games = prompt_int("Number of games (best-of-N style sampling, up to 100)", 10, 1, cfg.max_games)
    cfg.verbose = prompt_yes_no("Verbose play-by-play during sims", False)
    cfg.store_pbp = cfg.verbose or prompt_yes_no("Store play-by-play in memory (for last game report)", False)

    seed: Optional[int] = None
    if prompt_yes_no("Use a fixed random seed (repeatable results)", False):
        seed = prompt_int("Seed", 12345, 0, 10**9)

    # Build teams
    home = build_team(cfg, home_name)
    away = build_team(cfg, away_name)

    # If running a series, keep pbp storage modest (only last game) unless verbose
    if games > 1 and not cfg.verbose:
        cfg.store_pbp = False

    sr = run_series(cfg, home, away, games=games, seed=seed)
    print_series_report(sr, show_each_game=True)

    print("\nLAST GAME REPORT")
    last = sr.game_results[-1]
    print_game_report(last, include_pbp=prompt_yes_no("Show play-by-play for last game", cfg.verbose), pbp_limit=None)

    print("\nDone.")
