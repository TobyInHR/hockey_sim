import random
from typing import Dict, List, Optional, Tuple

from .config import SimConfig
from .models import DZ, NZ, OZ, GameState, MinorPenalty, Player, Goalie, Team
from .utils import (
    _key,
    avg_fatigue,
    clamp,
    fatigue_multiplier,
    goalie_fatigue_multiplier,
    log_event,
    other_team,
    r01_goalie,
    r01_player,
    start_shift,
    team_all_players,
    weighted_choice,
)


# ============================================================
# PENALTIES / MANPOWER
# ============================================================

def tick_penalties(pens: List[MinorPenalty], dt: int) -> None:
    for p in pens:
        p.remaining = max(0, p.remaining - dt)


def clear_expired_penalties(pens: List[MinorPenalty]) -> None:
    pens[:] = [p for p in pens if p.remaining > 0]


def penalized_id_set(pens: List[MinorPenalty]) -> set:
    return {id(p.player) for p in pens}


def manpower_counts(pens_home: List[MinorPenalty], pens_away: List[MinorPenalty], pulled_home: bool, pulled_away: bool) -> Tuple[int, int]:
    # base skaters: 5 - penalties; goalie pull adds +1 skater (regulation only, and only when actually pulled)
    home_skaters = max(3, 5 - len(pens_home)) + (1 if pulled_home else 0)
    away_skaters = max(3, 5 - len(pens_away)) + (1 if pulled_away else 0)

    # Keep minimums sane (OT handled separately)
    home_skaters = clamp(home_skaters, 3, 6)
    away_skaters = clamp(away_skaters, 3, 6)
    return int(home_skaters), int(away_skaters)


def desired_distribution(target: int) -> Tuple[int, int]:
    if target >= 6:
        return 4, 2
    if target == 5:
        return 3, 2
    if target == 4:
        return 2, 2
    return 1, 2


def build_on_ice(
    team: Team,
    f_idx: int,
    d_idx: int,
    target_skaters: int,
    pen_ids: set,
    rng: random.Random,
) -> List[Player]:
    base = (team.forwards[f_idx] + team.defense[d_idx])[:]
    on = [p for p in base if id(p) not in pen_ids]

    # trim down
    while len(on) > target_skaters:
        out = max(on, key=lambda p: p.fatigue)
        on.remove(out)

    # refill
    while len(on) < target_skaters:
        need_f, need_d = desired_distribution(target_skaters)
        cur_f = sum(1 for p in on if p.position == "F")
        cur_d = sum(1 for p in on if p.position == "D")
        pick_pos = "F" if cur_f < need_f else "D"

        on_ids = {id(p) for p in on}
        bench = [p for p in team_all_players(team) if id(p) not in on_ids and id(p) not in pen_ids and p.position == pick_pos]
        if not bench:
            bench = [p for p in team_all_players(team) if id(p) not in on_ids and id(p) not in pen_ids]
        if not bench:
            break

        bench.sort(key=lambda p: (1.25 - p.fatigue / 120.0), reverse=True)
        on.append(bench[0])

    return on


def special_teams_bonuses(pens_att: List[MinorPenalty], pens_def: List[MinorPenalty], att_pulled: bool, def_pulled: bool) -> Tuple[float, float]:
    """
    Returns (pp_bonus, pk_bonus) in 0..1 based on manpower diff.
    Note: pulling a goalie is treated as manpower advantage for the attacking team.
    """
    att_s = max(3, 5 - len(pens_att)) + (1 if att_pulled else 0)
    def_s = max(3, 5 - len(pens_def)) + (1 if def_pulled else 0)
    diff = att_s - def_s
    if diff > 0:
        return clamp(float(diff), 0.0, 2.0) / 2.0, 0.0
    if diff < 0:
        return 0.0, clamp(float(-diff), 0.0, 2.0) / 2.0
    return 0.0, 0.0


def pick_penalty_type(rng: random.Random, kind: str) -> str:
    if kind == "hit":
        return rng.choice(["boarding", "charging", "interference", "roughing"])
    return rng.choice(["hooking", "tripping", "holding", "slashing"])


def call_minor_penalty(
    cfg: SimConfig,
    pbp: List[str],
    penalized_team: Team,
    powerplay_team: Team,
    offender: Player,
    penalty_type: str,
    pens_against: List[MinorPenalty],
    clock: int,
) -> None:
    offender.penalties_taken += 1
    offender.pim += 2
    powerplay_team.pp_opportunities += 1
    pens_against.append(MinorPenalty(player=offender, remaining=120, penalty_type=penalty_type))
    log_event(cfg, pbp, clock, f"PENALTY {penalized_team.name}: {penalty_type} (2:00) offender={offender.name}")


def end_one_minor_on_pp_goal(pens: List[MinorPenalty]) -> Optional[MinorPenalty]:
    if not pens:
        return None
    pens.sort(key=lambda p: p.remaining)
    return pens.pop(0)


# ============================================================
# FACEOFFS / STOPPAGES
# ============================================================

def pick_faceoff_taker(on_ice: List[Player]) -> Player:
    centers = [p for p in on_ice if p.position == "F" and _key(p.slot) in ("c", "center")]
    if centers:
        return centers[0]
    return max(on_ice, key=lambda p: p.ratings.get("faceoffs", 50))


def faceoff_win_prob(a: Player, b: Player) -> float:
    ar = r01_player(a, "faceoffs", 50) * fatigue_multiplier(a)
    br = r01_player(b, "faceoffs", 50) * fatigue_multiplier(b)
    p = ar / (ar + br) if (ar + br) > 0 else 0.5
    return clamp(p, 0.35, 0.65)


def faceoff(rng: random.Random, home: Team, away: Team, home_on: List[Player], away_on: List[Player]) -> Team:
    taker_h = pick_faceoff_taker(home_on)
    taker_a = pick_faceoff_taker(away_on)
    p_home = faceoff_win_prob(taker_h, taker_a)

    if rng.random() < p_home:
        taker_h.faceoff_wins += 1
        taker_a.faceoff_losses += 1
        home.team_faceoff_wins += 1
        away.team_faceoff_losses += 1
        return home

    taker_a.faceoff_wins += 1
    taker_h.faceoff_losses += 1
    away.team_faceoff_wins += 1
    home.team_faceoff_losses += 1
    return away


def resolve_faceoff_location_relative(winner: Team, team_at_stoppage: Team, z: str) -> str:
    if z == NZ:
        return NZ
    if z == OZ:
        return OZ if winner is team_at_stoppage else DZ
    return DZ if winner is team_at_stoppage else OZ


def stoppage_probability_by_zone(zone: str) -> float:
    if zone == OZ:
        return 0.075
    if zone == NZ:
        return 0.070
    return 0.060


def pick_misc_stoppage_type(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.45:
        return "puck out of play"
    if r < 0.75:
        return "high stick"
    return "hand pass"


def do_stoppage(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
    label: str,
    faceoff_zone_relative_to_possessor: str,
    home_on: List[Player],
    away_on: List[Player],
) -> None:
    team_at_stoppage = state.possession
    log_event(cfg, pbp, state.clock, f"STOPPAGE: {label} (FO in {faceoff_zone_relative_to_possessor} rel {team_at_stoppage.name})")

    winner = faceoff(rng, home, away, home_on, away_on)

    state.oz_pressure = 0.0
    state.rebound_window = False
    state.possession = winner
    state.zone = resolve_faceoff_location_relative(winner, team_at_stoppage, faceoff_zone_relative_to_possessor)

    # Any stoppage ends a goalie pull immediately (simple + UI-friendly)
    home.goalie_pulled = False
    away.goalie_pulled = False
    state.home_pull_armed = False
    state.away_pull_armed = False

    log_event(cfg, pbp, state.clock, f"FACEOFF: {winner.name} wins, zone={state.zone}")


# ============================================================
# PRESSURE
# ============================================================

def update_pressure(state: GameState, dt: int, zone: str, gain_per_sec: float, decay_per_sec: float) -> None:
    if zone == OZ:
        state.oz_pressure = clamp(state.oz_pressure + gain_per_sec * dt, 0.0, 1.0)
    else:
        state.oz_pressure = clamp(state.oz_pressure - decay_per_sec * dt, 0.0, 1.0)


def pressure_spike(state: GameState, spike: float) -> None:
    state.oz_pressure = clamp(state.oz_pressure + spike, 0.0, 1.0)


# ============================================================
# ZONE STEP
# ============================================================

def step_zone_with_offside_check(
    rng: random.Random,
    zone: str,
    offside_prob: float,
    dz_to_nz_prob: float,
    nz_to_oz_prob: float,
    oz_hold_prob: float,
) -> Tuple[str, bool, bool]:
    if zone == DZ:
        return (NZ if rng.random() < dz_to_nz_prob else DZ), False, False

    if zone == NZ:
        if rng.random() < nz_to_oz_prob:
            if rng.random() < offside_prob:
                return NZ, True, False
            return OZ, False, True
        return NZ, False, False

    return (OZ if rng.random() < oz_hold_prob else NZ), False, False


# ============================================================
# RATED PLAYER EVENT SELECTION
# ============================================================

def pick_shooter(rng: random.Random, attackers: List[Player]) -> Player:
    def w(p: Player) -> float:
        pos_boost = 1.18 if p.position == "F" else 0.90
        sh = 0.55 + 0.80 * r01_player(p, "shooting", 60)
        oa = 0.70 + 0.55 * r01_player(p, "offensive_awareness", 60)
        acc = 0.75 + 0.40 * r01_player(p, "shooting_accuracy", 60)
        fresh = fatigue_multiplier(p)
        return pos_boost * sh * oa * acc * fresh
    return weighted_choice(rng, attackers, w)


def pick_blocker(rng: random.Random, defenders: List[Player]) -> Player:
    def w(p: Player) -> float:
        pos_boost = 1.35 if p.position == "D" else 1.0
        blk = 0.60 + 1.00 * r01_player(p, "shot_blocking", 60)
        da = 0.70 + 0.70 * r01_player(p, "defensive_awareness", 60)
        fresh = fatigue_multiplier(p)
        return pos_boost * blk * da * fresh
    return weighted_choice(rng, defenders, w)


def pick_takeaway_player(rng: random.Random, defenders: List[Player]) -> Player:
    def w(p: Player) -> float:
        da = 0.70 + 0.80 * r01_player(p, "defensive_awareness", 60)
        poke = 0.65 + 0.70 * r01_player(p, "poke_checking", 55)
        disc = 0.85 + 0.35 * r01_player(p, "discipline", 60)
        fresh = fatigue_multiplier(p)
        pos = 1.10 if p.position == "D" else 1.0
        return pos * da * poke * disc * fresh
    return weighted_choice(rng, defenders, w)


def pick_puck_carrier(rng: random.Random, attackers: List[Player]) -> Player:
    def w(p: Player) -> float:
        oa = 0.75 + 0.60 * r01_player(p, "offensive_awareness", 60)
        disc = 0.75 + 0.50 * r01_player(p, "discipline", 60)
        fresh = fatigue_multiplier(p)
        pos = 1.15 if p.position == "F" else 0.95
        return pos * oa * disc * fresh
    return weighted_choice(rng, attackers, w)


def pick_hitter(rng: random.Random, defenders: List[Player]) -> Player:
    def w(p: Player) -> float:
        hit = 0.60 + 0.90 * r01_player(p, "hitting", 60)
        disc = 0.85 + 0.35 * r01_player(p, "discipline", 60)
        fresh = fatigue_multiplier(p)
        pos = 1.15 if p.position == "D" else 1.0
        return pos * hit * disc * fresh
    return weighted_choice(rng, defenders, w)


def maybe_assists(rng: random.Random, shooter: Player, attackers: List[Player]) -> List[Player]:
    others = [p for p in attackers if p is not shooter]
    if not others:
        return []
    avg_oa = sum(r01_player(p, "offensive_awareness", 60) for p in others) / len(others)
    bump = (avg_oa - 0.5) * 0.10
    p0 = clamp(0.30 - bump, 0.15, 0.45)
    p2 = clamp(0.20 + bump, 0.10, 0.35)
    p1 = 1.0 - p0 - p2
    r = rng.random()
    if r < p0:
        return []
    if r < p0 + p1:
        return [rng.choice(others)]
    rng.shuffle(others)
    return others[:2]


# ============================================================
# LOCATION-BASED xG + GOALIE MODEL
# ============================================================

def choose_shot_location(rng: random.Random, weights: Dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = [max(1e-9, float(weights[k])) for k in keys]
    total = sum(vals)
    r = rng.random() * total
    run = 0.0
    for k, w in zip(keys, vals):
        run += w
        if r <= run:
            return k
    return keys[-1]


def shot_quality_xg(
    cfg: SimConfig,
    shooter: Player,
    state: GameState,
    pp_bonus: float,
    pk_bonus: float,
    location: str,
) -> float:
    sh = r01_player(shooter, "shooting", 60)
    oa = r01_player(shooter, "offensive_awareness", 60)
    acc = r01_player(shooter, "shooting_accuracy", 60)
    fresh = fatigue_multiplier(shooter)

    xg = cfg.base_xg_per_sog
    xg += cfg.pressure_xg_bonus * state.oz_pressure
    xg += cfg.pp_xg_bonus * pp_bonus
    xg += cfg.rebound_xg_bonus if state.rebound_window else 0.0

    # location multiplier
    xg *= cfg.loc_xg_mult.get(location, 1.0)

    # PK suppresses
    xg *= (1.0 - cfg.defense_pk_xg_suppression * pk_bonus)

    # shooter talent “compliments” base rather than dictates it
    xg *= (0.85 + 0.20 * sh + 0.10 * oa + 0.08 * acc) * (0.92 + 0.18 * fresh)

    return clamp(xg, 0.005, 0.45)


def goalie_save_chance(
    cfg: SimConfig,
    goalie: Goalie,
    xg: float,
    pressure: float,
    defending_team_fatigue: float,
    location: str,
) -> float:
    """
    Convert shot danger into a save chance:
    - baseline from xG
    - goalie skill, confidence, fatigue adjust
    """
    # “danger” is xG, plus context
    danger = clamp(xg, 0.0, 0.60)
    danger += 0.02 * pressure
    danger += 0.02 * clamp(defending_team_fatigue / 100.0, 0.0, 1.0)

    # goalie composite
    reflex = r01_goalie(goalie, "reflexes", 60)
    pos = r01_goalie(goalie, "positioning", 60)
    track = r01_goalie(goalie, "puck_tracking", 60)

    skill = (0.40 * reflex + 0.35 * pos + 0.25 * track)

    conf = clamp(goalie.confidence, 0.0, 1.0)
    fat_mult = goalie_fatigue_multiplier(goalie)

    # Higher danger reduces save chance; skill and confidence raise it; fatigue reduces it.
    save_chance = (1.0 - danger) * (0.70 + 0.45 * skill) * (0.85 + 0.30 * conf) * (0.85 + 0.20 * fat_mult)

    # keep in plausible bounds
    return clamp(save_chance, 0.20, 0.985)


def goalie_rebound_probability(cfg: SimConfig, goalie: Goalie, xg: float, pressure: float) -> float:
    rc = r01_goalie(goalie, "rebound_control", 60)
    fat = clamp(goalie.fatigue / 100.0, 0.0, 1.0)
    # more danger + pressure + fatigue increases rebound; rebound_control suppresses
    p = cfg.goalie_rebound_base
    p *= (1.0 + 1.10 * clamp(xg / 0.20, 0.0, 2.0))
    p *= (1.0 + 0.60 * pressure)
    p *= (1.0 + 0.35 * fat)
    p *= (1.25 - 0.55 * rc)
    return clamp(p, 0.02, 0.40)


def goalie_cover_probability(cfg: SimConfig, goalie: Goalie, xg: float, pressure: float, defending_team_fatigue: float) -> float:
    pos = r01_goalie(goalie, "positioning", 60)
    track = r01_goalie(goalie, "puck_tracking", 60)
    fat = clamp(goalie.fatigue / 100.0, 0.0, 1.0)
    team_fat = clamp(defending_team_fatigue / 100.0, 0.0, 1.0)

    # your rule: higher danger, higher team fatigue, higher pressure -> MORE likely cover
    p = cfg.goalie_cover_base
    p *= (1.0 + 1.25 * clamp(xg / 0.20, 0.0, 2.0))
    p *= (1.0 + 0.70 * pressure)
    p *= (1.0 + 0.55 * team_fat)
    p *= (1.0 + 0.35 * fat)

    # stronger tracking/positioning slightly helps control, which reduces “need to cover”
    p *= (1.05 - 0.15 * (0.5 * pos + 0.5 * track))

    return clamp(p, 0.05, 0.75)


def update_goalie_state_on_shot(goalie: Goalie, saved: bool, xg: float, dt: int) -> None:
    # fatigue ticks with time and with shots; endurance reduces it
    endu = r01_goalie(goalie, "endurance", 70)
    goalie.toi_seconds += dt
    goalie.fatigue = clamp(goalie.fatigue + (0.0020 * dt) * (1.05 - 0.35 * endu), 0.0, 100.0)

    # confidence nudges
    if saved:
        goalie.confidence = clamp(goalie.confidence + 0.015 * clamp(xg / 0.15, 0.5, 2.0), 0.0, 1.0)
    else:
        goalie.confidence = clamp(goalie.confidence - 0.030 * clamp(xg / 0.15, 0.5, 2.5), 0.0, 1.0)


# ============================================================
# UTILIZATION + LINE CHANGES (RATINGS + FATIGUE)
# ============================================================

def next_shift_length_seconds(rng: random.Random, shift_min: int, shift_mode: int, shift_max: int) -> int:
    return int(round(rng.triangular(shift_min, shift_max, shift_mode)))


def guardrail_usage_weight(unit_toi: int, time_so_far: int, bounds: Optional[Tuple[int, int]], full_game_seconds: int) -> float:
    if not bounds or time_so_far <= 0 or full_game_seconds <= 0:
        return 1.0
    projected = (unit_toi / max(1, time_so_far)) * full_game_seconds
    min_b, max_b = bounds
    if projected < min_b:
        gap = clamp((min_b - projected) / max(min_b, 1), 0.0, 0.60)
        return 1.0 + 0.90 * gap
    if projected > max_b:
        gap = clamp((projected - max_b) / max(max_b, 1), 0.0, 0.60)
        return clamp(1.0 - 0.90 * gap, 0.35, 1.0)
    return 1.0


def apply_bias_and_normalize(base_shares: List[float], bias: List[float]) -> List[float]:
    n = len(base_shares)
    b = bias[:] if bias is not None else [1.0] * n
    if len(b) != n:
        b = (b + [1.0] * n)[:n]
    raw = [max(1e-9, base_shares[i] * max(0.01, float(b[i]))) for i in range(n)]
    s = sum(raw)
    return [x / s for x in raw] if s > 0 else [1.0 / n] * n


def choose_unit_index(
    rng: random.Random,
    desired_shares: List[float],
    unit_toi: List[int],
    time_so_far: int,
    current_idx: int,
    utilization_strength: float,
    repeat_penalty: float,
    fatigue_bias_strength: float,
    unit_fatigues: List[float],
    min_weight: float,
    guardrails: Optional[List[Tuple[int, int]]],
    full_game_seconds: int,
) -> int:
    time_so_far = max(1, time_so_far)
    scores: List[float] = []
    for i, target in enumerate(desired_shares):
        actual = unit_toi[i] / time_so_far
        ratio = (target / max(actual, 1e-6))
        adj = 1.0 + utilization_strength * (ratio - 1.0)
        adj = clamp(adj, 0.25, 3.0)
        base = target * adj

        fat = unit_fatigues[i]
        fat_factor = clamp(1.10 - (fat / 140.0), 0.70, 1.12)
        fat_factor = 1.0 + fatigue_bias_strength * (fat_factor - 1.0)

        w = base * fat_factor
        if i == current_idx:
            w *= repeat_penalty

        bounds = guardrails[i] if guardrails and i < len(guardrails) else None
        w *= guardrail_usage_weight(unit_toi[i], time_so_far, bounds, full_game_seconds)

        scores.append(max(min_weight, w))

    total = sum(scores)
    r = rng.random() * total
    run = 0.0
    for i, sc in enumerate(scores):
        run += sc
        if r <= run:
            return i
    return len(desired_shares) - 1


def unit_avg_fatigue(team: Team, unit_type: str, idx: int) -> float:
    if unit_type == "F":
        return avg_fatigue(team.forwards[idx])
    return avg_fatigue(team.defense[idx])


def compute_shift_target_seconds(
    cfg: SimConfig,
    rng: random.Random,
    team: Team,
    opponent: Team,
    state: GameState,
    period_length: int,
    on_ice: List[Player],
) -> int:
    base = next_shift_length_seconds(rng, cfg.shift_min, cfg.shift_mode, cfg.shift_max)
    endu = sum(r01_player(p, "endurance", 70) for p in on_ice) / max(1, len(on_ice))
    endurance_factor = clamp(1.0 + cfg.shift_endurance_weight * (endu - 0.5), 0.85, 1.20)

    elapsed = (state.period - 1) * period_length + state.clock
    context_factor = 1.0
    if elapsed >= cfg.shift_late_game_minute * 60:
        diff = team.goals - opponent.goals
        if diff < 0:
            context_factor *= cfg.shift_trailing_longer_mult
        elif diff > 0:
            context_factor *= cfg.shift_leading_shorter_mult

    pressure_factor = cfg.shift_pressure_push_mult if state.zone == OZ else cfg.shift_pressure_relief_mult
    pressure_factor = 1.0 + (pressure_factor - 1.0) * state.oz_pressure

    target = base * endurance_factor * context_factor * pressure_factor
    if state.oz_pressure >= cfg.caught_on_pressure_threshold and rng.random() < cfg.caught_on_chance:
        target *= cfg.caught_on_extension_mult

    return int(clamp(target, cfg.shift_min * 0.80, cfg.shift_max * 1.50))


def average_shift_elapsed(on_ice: List[Player]) -> float:
    return sum(p.shift_seconds_current for p in on_ice) / max(1, len(on_ice))


def apply_line_change(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    team: Team,
    is_home: bool,
    state: GameState,
    clock_in_period: int,
    period_length: int,
    team_target_skaters: int,
    opp_target_skaters: int,
) -> None:
    time_so_far = (state.period - 1) * period_length + clock_in_period
    time_so_far = max(1, time_so_far)
    full_game_seconds = 60 * 60

    cur_f = state.home_f_idx if is_home else state.away_f_idx
    cur_d = state.home_d_idx if is_home else state.away_d_idx

    sit = "EV"
    if team_target_skaters > opp_target_skaters:
        sit = "PP"
        f_shares = apply_bias_and_normalize(cfg.desired_f_shares, cfg.pp_f_bias)
        d_shares = apply_bias_and_normalize(cfg.desired_d_shares, cfg.pp_d_bias)
    elif team_target_skaters < opp_target_skaters:
        sit = "PK"
        f_shares = apply_bias_and_normalize(cfg.desired_f_shares, cfg.pk_f_bias)
        d_shares = apply_bias_and_normalize(cfg.desired_d_shares, cfg.pk_d_bias)
    else:
        f_shares = cfg.desired_f_shares
        d_shares = cfg.desired_d_shares

    f_fats = [unit_avg_fatigue(team, "F", i) for i in range(4)]
    d_fats = [unit_avg_fatigue(team, "D", i) for i in range(3)]

    new_f = choose_unit_index(
        rng, f_shares, team.f_line_toi, time_so_far, cur_f,
        cfg.utilization_strength_f, cfg.repeat_penalty_f, cfg.fatigue_bias_strength_f,
        f_fats, cfg.min_weight, cfg.toi_guardrails_f, full_game_seconds
    )
    new_d = choose_unit_index(
        rng, d_shares, team.d_pair_toi, time_so_far, cur_d,
        cfg.utilization_strength_d, cfg.repeat_penalty_d, cfg.fatigue_bias_strength_d,
        d_fats, cfg.min_weight, cfg.toi_guardrails_d, full_game_seconds
    )

    if new_f == cur_f and new_d == cur_d:
        return

    if is_home:
        state.home_f_idx = new_f
        state.home_d_idx = new_d
    else:
        state.away_f_idx = new_f
        state.away_d_idx = new_d

    log_event(cfg, pbp, state.clock, f"{team.name} change ({sit}) -> F{new_f+1} D{new_d+1}")


# ============================================================
# FATIGUE (SKATERS)
# ============================================================

def update_player_fatigue(
    all_players: List[Player],
    on_ice_ids: set,
    dt: int,
    base_gain_per_sec: float,
    base_recover_per_sec: float,
    endurance_gain_scale: float,
    endurance_recover_scale: float,
) -> None:
    for p in all_players:
        endu = r01_player(p, "endurance", 70)
        if id(p) in on_ice_ids:
            gain = base_gain_per_sec * (1.0 + endurance_gain_scale * (0.65 - endu))
            p.fatigue = clamp(p.fatigue + gain * dt, 0.0, 100.0)
        else:
            rec = base_recover_per_sec * (0.75 + endurance_recover_scale * endu)
            p.fatigue = clamp(p.fatigue - rec * dt, 0.0, 100.0)


# ============================================================
# TURNOVERS / HITS / PENALTIES (RATING-AWARE)
# ============================================================

def resolve_turnover_event(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
    enable_penalties: bool,
    pens_home: List[MinorPenalty],
    pens_away: List[MinorPenalty],
    home_on: List[Player],
    away_on: List[Player],
    pp_bonus: float,
    pk_bonus: float,
) -> bool:
    attacking = state.possession
    defending = other_team(attacking, home, away)

    attackers = home_on if attacking is home else away_on
    defenders = away_on if attacking is home else home_on

    carrier = pick_puck_carrier(rng, attackers)
    taker = pick_takeaway_player(rng, defenders)
    hitter = pick_hitter(rng, defenders)

    carrier_slop = (1.15 - 0.70 * r01_player(carrier, "offensive_awareness", 60)) * (1.10 - 0.55 * r01_player(carrier, "discipline", 60))
    defender_skill = (0.85 + 0.80 * r01_player(taker, "defensive_awareness", 60)) * (0.80 + 0.70 * r01_player(taker, "poke_checking", 55))
    hit_force = (0.85 + 0.85 * r01_player(hitter, "hitting", 60))

    forced_bonus = (cfg.pressure_forced_play_bonus * state.oz_pressure) if state.zone == OZ else 0.0

    g = cfg.turnover_giveaway_share * carrier_slop * (1.0 - 0.40 * forced_bonus)
    t = cfg.turnover_takeaway_share * defender_skill * (1.0 + 0.70 * forced_bonus)
    h = cfg.turnover_hit_share * hit_force * (1.0 + 0.90 * forced_bonus)

    s = max(1e-9, g + t + h)
    g, t, h = g / s, t / s, h / s

    r = rng.random()

    # In NZ, convert some giveaway-type turnovers into “failed entries” (no giveaway charged)
    if state.zone == NZ:
        failed_entry_prob = clamp(g * cfg.failed_entry_from_giveaway_fraction, 0.0, 0.90)
        if r < failed_entry_prob:
            log_event(cfg, pbp, state.clock, f"FAILED ENTRY by {attacking.name} (no giveaway)")
            state.possession = defending
            state.oz_pressure = 0.0
            state.rebound_window = False
            return False
        r = (r - failed_entry_prob) / max(1e-9, (1.0 - failed_entry_prob))

    if r < g:
        carrier.giveaways += 1
        attacking.giveaways += 1
        log_event(cfg, pbp, state.clock, f"GIVEAWAY {attacking.name} by {carrier.name}")
        state.possession = defending
        state.oz_pressure = 0.0
        state.rebound_window = False
        return False

    if r < g + t:
        taker.takeaways += 1
        defending.takeaways += 1
        log_event(cfg, pbp, state.clock, f"TAKEAWAY {defending.name} by {taker.name} from {carrier.name}")

        if enable_penalties:
            disc = r01_player(taker, "discipline", 60)
            tired = 1.0 - fatigue_multiplier(taker)
            p = cfg.penalty_base_takeaway * cfg.defending_penalty_bias * (1.10 - 0.80 * disc) * (1.0 + 0.70 * tired)
            if state.zone == OZ:
                p *= 1.25
            if rng.random() < clamp(p, 0.0, 0.35):
                ptype = pick_penalty_type(rng, "stick")
                if defending is home:
                    call_minor_penalty(cfg, pbp, home, away, taker, ptype, pens_home, state.clock)
                else:
                    call_minor_penalty(cfg, pbp, away, home, taker, ptype, pens_away, state.clock)
                return True

        state.possession = defending
        state.oz_pressure = 0.0
        state.rebound_window = False
        return False

    hitter.hits += 1
    defending.hits += 1
    log_event(cfg, pbp, state.clock, f"HIT {defending.name} by {hitter.name} on {carrier.name}")

    if enable_penalties:
        disc = r01_player(hitter, "discipline", 60)
        tired = 1.0 - fatigue_multiplier(hitter)
        p = cfg.penalty_base_hit * cfg.defending_penalty_bias * (1.10 - 0.80 * disc) * (1.0 + 0.70 * tired)
        if rng.random() < clamp(p, 0.0, 0.35):
            ptype = pick_penalty_type(rng, "hit")
            if defending is home:
                call_minor_penalty(cfg, pbp, home, away, hitter, ptype, pens_home, state.clock)
            else:
                call_minor_penalty(cfg, pbp, away, home, hitter, ptype, pens_away, state.clock)
            return True

    # hit-caused turnover chance
    hit_skill = r01_player(hitter, "hitting", 60)
    victim_balance = 0.55 * r01_player(carrier, "offensive_awareness", 60) + 0.45 * r01_player(carrier, "discipline", 60)
    p_turn = 0.18 + 0.28 * hit_skill + 0.10 * (1.0 - victim_balance) + 0.08 * (carrier.fatigue / 100.0)
    p_turn *= (1.0 + 0.20 * state.oz_pressure) if state.zone == OZ else 1.0
    if rng.random() < clamp(p_turn, 0.10, 0.65):
        log_event(cfg, pbp, state.clock, "HIT causes turnover")
        state.possession = defending
        state.oz_pressure = 0.0
        state.rebound_window = False

    return False


# ============================================================
# GOALIE PULL (6v5) REGULATION ONLY
# ============================================================

def maybe_arm_goalie_pull(cfg: SimConfig, state: GameState, home: Team, away: Team, period_length: int) -> None:
    # Only third period regulation (period==3), only if trailing by <=2, only after 3:00 remaining.
    if state.period != 3:
        state.home_pull_armed = False
        state.away_pull_armed = False
        return

    seconds_left = period_length - state.clock
    if seconds_left > cfg.pull_start_seconds_left:
        state.home_pull_armed = False
        state.away_pull_armed = False
        return

    deficit_home = away.goals - home.goals
    deficit_away = home.goals - away.goals

    state.home_pull_armed = (deficit_home >= 1 and deficit_home <= cfg.pull_max_deficit)
    state.away_pull_armed = (deficit_away >= 1 and deficit_away <= cfg.pull_max_deficit)


def maybe_execute_goalie_pull(cfg: SimConfig, pbp: List[str], state: GameState, team: Team) -> None:
    # Pull occurs on next OZ possession (regulation-only rule already ensured by arming)
    if team.goalie_pulled:
        return
    armed = state.home_pull_armed if team is state.possession else state.away_pull_armed
    if not armed:
        return
    if state.zone != OZ:
        return

    team.goalie_pulled = True
    log_event(cfg, pbp, state.clock, f"GOALIE PULLED: {team.name} (6v5)")

    # Once pulled, we keep it until stoppage/goal/possession ends (possession end handled in stoppage and turnovers/shots)
    if team is state.possession:
        if team.name == team.name:  # no-op; keep structure obvious
            pass


def end_goalie_pull_on_possession_loss(home: Team, away: Team, new_possessor: Team) -> None:
    # Simple: if you lose possession with goalie pulled, we assume you regroup and put goalie back immediately.
    if home.goalie_pulled and new_possessor is away:
        home.goalie_pulled = False
    if away.goalie_pulled and new_possessor is home:
        away.goalie_pulled = False


# ============================================================
# SHOT RESOLUTION (BLOCK/MISS/SAVE/GOAL) + GOALIE PULL END
# ============================================================

def resolve_blocked_attempt(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
) -> None:
    attacking = state.possession
    defending = other_team(attacking, home, away)
    state.rebound_window = False

    if rng.random() < cfg.block_attacking_recover_prob:
        state.zone = OZ
        log_event(cfg, pbp, state.clock, f"BLOCK recovery: {attacking.name} keeps it in OZ")
        return

    # defending recovers
    new_possessor = defending
    state.possession = new_possessor
    state.oz_pressure = 0.0
    end_goalie_pull_on_possession_loss(home, away, new_possessor)

    if rng.random() < cfg.block_defender_clear_to_nz_prob:
        state.zone = NZ
        log_event(cfg, pbp, state.clock, f"Clear after block -> {new_possessor.name} possession, zone=NZ")
    else:
        state.zone = DZ
        log_event(cfg, pbp, state.clock, f"Control after block -> {new_possessor.name} possession, zone=DZ")


def resolve_missed_attempt(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
    home_on: List[Player],
    away_on: List[Player],
) -> None:
    attacking = state.possession
    defending = other_team(attacking, home, away)
    state.rebound_window = False

    r = rng.random()
    if r < cfg.miss_stays_in_oz_prob:
        state.zone = OZ
        log_event(cfg, pbp, state.clock, f"MISS stays in OZ for {attacking.name}")
        return

    if r < cfg.miss_stays_in_oz_prob + cfg.miss_stoppage_prob:
        do_stoppage(cfg, pbp, rng, home, away, state, "puck out of play (miss)", OZ, home_on, away_on)
        return

    new_possessor = defending
    state.possession = new_possessor
    state.oz_pressure = 0.0
    end_goalie_pull_on_possession_loss(home, away, new_possessor)
    state.zone = DZ
    log_event(cfg, pbp, state.clock, f"Defending recovers miss -> {new_possessor.name} possession, zone=DZ")


def maybe_oz_clear_attempt(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
    pk_bonus: float,
    home_on: List[Player],
    away_on: List[Player],
) -> bool:
    if state.zone != OZ:
        return False

    eff_attempt = cfg.oz_clear_attempt_prob * (1.0 + 0.25 * pk_bonus)
    if rng.random() >= eff_attempt:
        return False

    attacking = state.possession
    defending = other_team(attacking, home, away)
    defenders = home_on if defending is home else away_on

    da = sum(r01_player(p, "defensive_awareness", 60) * fatigue_multiplier(p) for p in defenders) / max(1, len(defenders))
    eff_success = cfg.oz_clear_success_prob * (0.80 + 0.50 * da) * (1.0 + 0.20 * pk_bonus)
    eff_success = clamp(eff_success * (1.0 - cfg.pressure_clear_success_down * state.oz_pressure), 0.05, 0.98)

    log_event(cfg, pbp, state.clock, f"OZ clear attempt by {defending.name} (pressure={state.oz_pressure:.2f})")

    state.rebound_window = False

    if rng.random() < eff_success:
        state.possession = defending
        state.oz_pressure = clamp(state.oz_pressure - cfg.pressure_relief_on_clear_success, 0.0, 1.0)
        end_goalie_pull_on_possession_loss(home, away, defending)
        state.zone = NZ
        log_event(cfg, pbp, state.clock, f"Clear SUCCESS -> {defending.name} possession, zone=NZ")
    else:
        state.zone = OZ
        log_event(cfg, pbp, state.clock, f"Clear FAIL -> {attacking.name} keeps pressure, zone=OZ")

    return True


def resolve_save_outcome(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    state: GameState,
    attacking: Team,
    defending: Team,
    defending_goalie: Goalie,
    xg: float,
    location: str,
    home_on: List[Player],
    away_on: List[Player],
) -> None:
    # goalie decides rebound vs cover vs controlled based on your drivers
    defenders = home_on if defending is home else away_on
    team_fat = avg_fatigue(defenders)

    p_reb = goalie_rebound_probability(cfg, defending_goalie, xg, state.oz_pressure)
    p_cov = goalie_cover_probability(cfg, defending_goalie, xg, state.oz_pressure, team_fat)

    # ensure they fit under 1.0
    scale = max(1.0, p_reb + p_cov)
    p_reb /= scale
    p_cov /= scale

    r = rng.random()

    if r < p_reb:
        defending_goalie.rebounds_allowed += 1
        log_event(cfg, pbp, state.clock, "SAVE -> REBOUND")

        # Rebound recovery: baseline 55% (your earlier), modestly helped by pressure and attacking OA
        attackers = home_on if attacking is home else away_on
        att_oa = sum(r01_player(p, "offensive_awareness", 60) * fatigue_multiplier(p) for p in attackers) / max(1, len(attackers))
        def_da = sum(r01_player(p, "defensive_awareness", 60) * fatigue_multiplier(p) for p in defenders) / max(1, len(defenders))

        p_att = 0.55 + 0.10 * (att_oa - def_da) + 0.08 * state.oz_pressure
        p_att = clamp(p_att, 0.25, 0.80)

        if rng.random() < p_att:
            state.zone = OZ
            state.rebound_window = True
            log_event(cfg, pbp, state.clock, f"Rebound recovered by {attacking.name} (OZ continues)")
            return

        # defending recovers
        state.possession = defending
        state.oz_pressure = 0.0
        end_goalie_pull_on_possession_loss(home, away, defending)
        state.zone = DZ
        state.rebound_window = False
        log_event(cfg, pbp, state.clock, f"Rebound recovered by {defending.name} -> zone=DZ")
        return

    if r < p_reb + p_cov:
        defending_goalie.covers += 1
        log_event(cfg, pbp, state.clock, "SAVE + COVER -> stoppage")
        do_stoppage(cfg, pbp, rng, home, away, state, "goalie cover", OZ, home_on, away_on)
        return

    log_event(cfg, pbp, state.clock, f"Controlled SAVE -> {defending.name} gains possession")
    state.possession = defending
    state.oz_pressure = 0.0
    end_goalie_pull_on_possession_loss(home, away, defending)
    state.zone = DZ
    state.rebound_window = False


# ============================================================
# GOALIE PULL + GOALIE SWITCH LOGIC
# ============================================================

def current_goalie(team: Team) -> Goalie:
    # starter is index 0; if swapped, we move backup to index 0 permanently
    return team.goalies[0]


def maybe_switch_goalie(team: Team, period_no: int, goals_against_this_period: int, home: Team, away: Team, cfg: SimConfig, pbp: List[str], clock: int) -> None:
    # Simple rules:
    # - backup if starter allows 3 in one period
    # - backup if starter allows 4-6 total before the third period
    if len(team.goalies) < 2:
        return
    starter = team.goalies[0]
    backup = team.goalies[1]
    if not starter.is_starter:
        return  # already switched

    total_ga = starter.goals_against
    if goals_against_this_period >= 3:
        # switch now
        team.goalies = [backup, starter]
        team.goalies[0].is_starter = True
        team.goalies[1].is_starter = False
        log_event(cfg, pbp, clock, f"GOALIE SWITCH: {team.name} pulls starter {starter.name} -> backup {backup.name} (3 GA in period)")
        return

    if period_no < 3 and total_ga >= 4:
        team.goalies = [backup, starter]
        team.goalies[0].is_starter = True
        team.goalies[1].is_starter = False
        log_event(cfg, pbp, clock, f"GOALIE SWITCH: {team.name} pulls starter {starter.name} -> backup {backup.name} (GA={total_ga} before P3)")
        return
