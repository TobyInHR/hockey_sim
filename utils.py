import random
from typing import Dict, List

from .models import Player, Goalie, Team


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def fmt_toi(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def _norm(s: str) -> str:
    return (s or "").strip()


def _key(s: str) -> str:
    return _norm(s).lower()


def _parse_int(x: str, default: int = 60) -> int:
    try:
        return int(float((x or "").strip()))
    except Exception:
        return default


def r01_from_rating(val: int) -> float:
    # IMPORTANT: ratings are 0..100, but 0 is still “NHL-level floor” in effect.
    # We map 0 -> 0.35, 100 -> 1.0 so players “compliment” outcomes without dictating them.
    return clamp(0.35 + 0.65 * (clamp(val, 0, 100) / 100.0), 0.35, 1.0)


def r01_player(p: Player, key: str, default: int = 60) -> float:
    return r01_from_rating(p.ratings.get(key, default))


def r01_goalie(g: Goalie, key: str, default: int = 60) -> float:
    return r01_from_rating(g.ratings.get(key, default))


def other_team(team: Team, home: Team, away: Team) -> Team:
    return away if team is home else home


def team_all_players(team: Team) -> List[Player]:
    return [p for line in team.forwards for p in line] + [p for pair in team.defense for p in pair]


def start_shift(players: List[Player]) -> None:
    for p in players:
        p.shifts += 1


def add_toi(players: List[Player], dt: int) -> None:
    for p in players:
        p.toi_seconds += dt


def fatigue_multiplier(p: Player) -> float:
    return clamp(1.0 - (p.fatigue / 220.0), 0.70, 1.00)


def goalie_fatigue_multiplier(g: Goalie) -> float:
    return clamp(1.0 - (g.fatigue / 260.0), 0.75, 1.00)


def avg_fatigue(players: List[Player]) -> float:
    return sum(p.fatigue for p in players) / len(players) if players else 0.0


def log_event(cfg, pbp: List[str], clock: int, msg: str) -> None:
    line = f"[{mmss(clock)}] {msg}"
    if cfg.store_pbp:
        pbp.append(line)
    if cfg.verbose:
        print(line)


def weighted_choice(rng: random.Random, players: List[Player], weight_fn) -> Player:
    total = 0.0
    wts = []
    for p in players:
        w = max(0.0001, float(weight_fn(p)))
        wts.append(w)
        total += w
    r = rng.random() * total
    run = 0.0
    for p, w in zip(players, wts):
        run += w
        if r <= run:
            return p
    return players[-1]
