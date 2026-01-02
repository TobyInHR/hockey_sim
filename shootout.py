import random
from typing import List, Tuple

from .config import SimConfig
from .models import ShootoutAttempt, Team
from .gameplay import current_goalie
from .utils import clamp, log_event, r01_goalie, r01_player, team_all_players


def shootout(cfg: SimConfig, pbp: List[str], rng: random.Random, home: Team, away: Team) -> Tuple[str, List[ShootoutAttempt]]:
    log: List[ShootoutAttempt] = []
    home_score = 0
    away_score = 0

    def pick_shooter_team(team: Team, used: set):
        pool = [p for p in team_all_players(team) if p.position == "F"]

        # weight toward shooters
        def w(p):
            return (0.8 + 0.8 * r01_player(p, "shooting", 60) + 0.4 * r01_player(p, "shooting_accuracy", 60))

        pool.sort(key=w, reverse=True)
        for p in pool:
            if p.name not in used:
                return p
        return pool[0]

    used_home = set()
    used_away = set()

    g_home = current_goalie(home)
    g_away = current_goalie(away)

    def attempt(shooter_team: Team, goalie_team: Team, shooter, goalie) -> bool:
        # simple, ratings-informed, not credited
        sh = r01_player(shooter, "shooting", 60)
        acc = r01_player(shooter, "shooting_accuracy", 60)
        reflex = r01_goalie(goalie, "reflexes", 60)
        pos = r01_goalie(goalie, "positioning", 60)

        base = 0.33
        p_goal = base * (0.85 + 0.35 * sh + 0.20 * acc) * (1.05 - 0.25 * reflex) * (1.05 - 0.18 * pos)
        p_goal = clamp(p_goal, 0.05, 0.65)
        return rng.random() < p_goal

    rounds = cfg.shootout_rounds
    for r in range(1, rounds + 1):
        hs = pick_shooter_team(home, used_home)
        used_home.add(hs.name)
        scored = attempt(home, away, hs, g_away)
        log.append(ShootoutAttempt(shooter_team=home.name, shooter=hs.name, goalie_team=away.name, goalie=g_away.name, scored=scored))
        log_event(cfg, pbp, 0, f"SO R{r}: {home.name} shooter={hs.name} vs {g_away.name} -> {'GOAL' if scored else 'SAVE'}")
        if scored:
            home_score += 1

        as_ = pick_shooter_team(away, used_away)
        used_away.add(as_.name)
        scored = attempt(away, home, as_, g_home)
        log.append(ShootoutAttempt(shooter_team=away.name, shooter=as_.name, goalie_team=home.name, goalie=g_home.name, scored=scored))
        log_event(cfg, pbp, 0, f"SO R{r}: {away.name} shooter={as_.name} vs {g_home.name} -> {'GOAL' if scored else 'SAVE'}")
        if scored:
            away_score += 1

        # early win check after each full round
        if r == rounds:
            break

    # extra rounds sudden death
    extra = 0
    while home_score == away_score and extra < cfg.shootout_max_extra_rounds:
        extra += 1
        hs = pick_shooter_team(home, used_home)
        used_home.add(hs.name)
        h_goal = attempt(home, away, hs, g_away)
        log.append(ShootoutAttempt(shooter_team=home.name, shooter=hs.name, goalie_team=away.name, goalie=g_away.name, scored=h_goal))
        log_event(cfg, pbp, 0, f"SO SD{extra}: {home.name} shooter={hs.name} -> {'GOAL' if h_goal else 'SAVE'}")

        as_ = pick_shooter_team(away, used_away)
        used_away.add(as_.name)
        a_goal = attempt(away, home, as_, g_home)
        log.append(ShootoutAttempt(shooter_team=away.name, shooter=as_.name, goalie_team=home.name, goalie=g_home.name, scored=a_goal))
        log_event(cfg, pbp, 0, f"SO SD{extra}: {away.name} shooter={as_.name} -> {'GOAL' if a_goal else 'SAVE'}")

        if h_goal and not a_goal:
            return home.name, log
        if a_goal and not h_goal:
            return away.name, log

    # fallback (should not happen often)
    return (home.name if rng.random() < 0.5 else away.name), log
