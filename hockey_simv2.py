import csv
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# ============================================================
# 0) CONSTANTS
# ============================================================

DZ = "DZ"
NZ = "NZ"
OZ = "OZ"


# ============================================================
# 1) DATA MODELS
# ============================================================

@dataclass
class Player:
    name: str
    team: str
    position: str          # "F" or "D"
    unit_type: str         # "F" or "D"
    unit_no: int           # 1..4 for forwards, 1..3 for defense
    slot: str              # LW/C/RW or W1/W2/C; LD/RD or D1/D2
    ratings: Dict[str, int]

    # Stats
    goals: int = 0
    assists: int = 0
    shots: int = 0
    shot_attempts: int = 0
    blocks: int = 0

    giveaways: int = 0
    takeaways: int = 0
    hits: int = 0

    faceoff_wins: int = 0
    faceoff_losses: int = 0

    # Penalties (skater table only)
    penalties_taken: int = 0
    pim: int = 0

    # Usage (kept for engine, not shown in skater table)
    toi_seconds: int = 0
    shifts: int = 0
    fatigue: float = 0.0   # 0..100
    xg: float = 0.0


@dataclass
class Goalie:
    name: str
    team: str
    is_starter: bool
    ratings: Dict[str, int]

    # Dynamic state
    fatigue: float = 0.0       # 0..100
    confidence: float = 0.50   # 0..1

    # Stats (shootout goals do NOT count)
    goals_against: int = 0
    shots_against: int = 0
    saves: int = 0
    rebounds_allowed: int = 0
    covers: int = 0

    toi_seconds: int = 0

    def reset_game_state(self) -> None:
        self.fatigue = 0.0
        self.confidence = 0.50
        self.goals_against = 0
        self.shots_against = 0
        self.saves = 0
        self.rebounds_allowed = 0
        self.covers = 0
        self.toi_seconds = 0


@dataclass
class Team:
    name: str
    forwards: List[List[Player]]  # 4 x [3 players]
    defense: List[List[Player]]   # 3 x [2 players]
    goalies: List[Goalie]         # [starter, backup]

    # Team totals (report-friendly subset only)
    goals: int = 0
    shots: int = 0
    shot_attempts: int = 0
    shots_blocked_against: int = 0

    giveaways: int = 0
    takeaways: int = 0
    hits: int = 0

    pp_opportunities: int = 0
    pp_goals: int = 0

    team_faceoff_wins: int = 0
    team_faceoff_losses: int = 0

    xg: float = 0.0

    # Unit utilization (5v5 regulation only)
    f_line_toi: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    d_pair_toi: List[int] = field(default_factory=lambda: [0, 0, 0])

    # Goalie pull state
    goalie_pulled: bool = False

    def reset_game_state(self) -> None:
        self.goals = 0
        self.shots = 0
        self.shot_attempts = 0
        self.shots_blocked_against = 0
        self.giveaways = 0
        self.takeaways = 0
        self.hits = 0
        self.pp_opportunities = 0
        self.pp_goals = 0
        self.team_faceoff_wins = 0
        self.team_faceoff_losses = 0
        self.xg = 0.0
        self.f_line_toi = [0, 0, 0, 0]
        self.d_pair_toi = [0, 0, 0]
        self.goalie_pulled = False

        for line in self.forwards:
            for p in line:
                p.goals = p.assists = p.shots = p.shot_attempts = p.blocks = 0
                p.giveaways = p.takeaways = p.hits = 0
                p.faceoff_wins = p.faceoff_losses = 0
                p.penalties_taken = p.pim = 0
                p.toi_seconds = 0
                p.shifts = 0
                p.fatigue = 0.0
                p.xg = 0.0

        for pair in self.defense:
            for p in pair:
                p.goals = p.assists = p.shots = p.shot_attempts = p.blocks = 0
                p.giveaways = p.takeaways = p.hits = 0
                p.faceoff_wins = p.faceoff_losses = 0
                p.penalties_taken = p.pim = 0
                p.toi_seconds = 0
                p.shifts = 0
                p.fatigue = 0.0
                p.xg = 0.0

        for g in self.goalies:
            g.reset_game_state()


@dataclass
class MinorPenalty:
    player: Player
    remaining: int
    penalty_type: str


@dataclass
class GameState:
    period: int
    clock: int
    possession: Team
    zone: str

    home_f_idx: int = 0
    home_d_idx: int = 0
    away_f_idx: int = 0
    away_d_idx: int = 0

    home_next_change: int = 0
    away_next_change: int = 0

    oz_pressure: float = 0.0
    rebound_window: bool = False

    # goalie pull intent
    home_pull_armed: bool = False
    away_pull_armed: bool = False


@dataclass
class ShootoutAttempt:
    shooter_team: str
    shooter: str
    goalie_team: str
    goalie: str
    scored: bool


@dataclass
class GameResult:
    home: str
    away: str

    home_goals: int
    away_goals: int

    home_goals_by_period: List[int]
    away_goals_by_period: List[int]

    went_to_ot: bool
    ot_winner: Optional[str] = None

    went_to_so: bool = False
    so_winner: Optional[str] = None
    shootout_log: List[ShootoutAttempt] = field(default_factory=list)

    # Team summary (subset)
    team_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Skater tables (subset + PIM included)
    skaters: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Goalie table
    goalies: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Optional play-by-play
    pbp: List[str] = field(default_factory=list)


@dataclass
class SimConfig:
    # --- roster files
    skaters_csv_path: str = "rosters.csv"
    goalies_csv_path: str = "goalies.csv"

    # --- series
    max_games: int = 100

    # --- logging
    verbose: bool = True
    store_pbp: bool = True

    # --- core knobs (your “good results” set)
    base_turnover_prob: float = 0.18

    base_shot_attempt_prob: float = 0.50
    base_on_goal_prob: float = 0.55
    base_shot_blocked_prob: float = 0.20

    dz_to_nz_prob: float = 0.65
    nz_to_oz_prob: float = 0.90
    oz_hold_prob: float = 0.85

    offside_prob_on_entry: float = 0.040
    icing_prob_in_dz: float = 0.020
    misc_faceoff_same_zone_prob: float = 0.70

    block_attacking_recover_prob: float = 0.42
    block_defender_clear_to_nz_prob: float = 0.55
    miss_stays_in_oz_prob: float = 0.90
    miss_stoppage_prob: float = 0.08

    oz_clear_attempt_prob: float = 0.10
    oz_clear_success_prob: float = 0.20

    desired_f_shares: List[float] = field(default_factory=lambda: [0.40, 0.30, 0.20, 0.10])
    desired_d_shares: List[float] = field(default_factory=lambda: [0.50, 0.40, 0.10])

    utilization_strength_f: float = 0.75
    utilization_strength_d: float = 0.75
    repeat_penalty_f: float = 0.60
    repeat_penalty_d: float = 0.60
    min_weight: float = 0.0005

    fatigue_bias_strength_f: float = 0.60
    fatigue_bias_strength_d: float = 0.60

    shift_min: int = 45
    shift_mode: int = 60
    shift_max: int = 90

    fat_gain_base: float = 0.030
    fat_recover_base: float = 0.022
    endurance_gain_scale: float = 0.70
    endurance_recover_scale: float = 0.80

    pressure_gain_per_sec: float = 0.010
    pressure_decay_per_sec: float = 0.016
    pressure_shot_attempt_up: float = 0.35
    pressure_clear_success_down: float = 0.55
    pressure_spike_on_attempt: float = 0.020
    pressure_spike_on_sog: float = 0.030
    pressure_relief_on_clear_success: float = 0.15

    turnover_giveaway_share: float = 0.55
    turnover_takeaway_share: float = 0.30
    turnover_hit_share: float = 0.15
    pressure_forced_play_bonus: float = 0.80
    failed_entry_from_giveaway_fraction: float = 0.50  # kept for internal mix; not shown as a team stat

    enable_penalties_regulation: bool = True
    enable_penalties_ot: bool = False  # decision: no OT penalties
    penalty_base_hit: float = 0.10
    penalty_base_takeaway: float = 0.10
    defending_penalty_bias: float = 1.35

    pp_shot_attempt_bonus: float = 0.55
    pp_on_goal_bonus: float = 0.10
    pp_pressure_gain_bonus: float = 0.60
    pk_clear_bonus: float = 0.60

    pp_f_bias: List[float] = field(default_factory=lambda: [1.60, 1.30, 0.85, 0.55])
    pp_d_bias: List[float] = field(default_factory=lambda: [1.45, 1.15, 0.75])
    pk_f_bias: List[float] = field(default_factory=lambda: [0.90, 1.00, 1.15, 1.25])
    pk_d_bias: List[float] = field(default_factory=lambda: [1.55, 1.25, 0.80])

    league_avg_save_pct: float = 0.910  # used as “league baseline” for goalie adjustment
    base_xg_per_sog: float = 0.075
    pressure_xg_bonus: float = 0.060
    pp_xg_bonus: float = 0.085
    rebound_xg_bonus: float = 0.50
    defense_pk_xg_suppression: float = 0.20

    # --- location-based xG (simple lane model)
    # weights represent how often each location is selected in OZ
    loc_weights: Dict[str, float] = field(default_factory=lambda: {"POINT": 0.35, "CIRCLE": 0.40, "SLOT": 0.25})
    loc_xg_mult: Dict[str, float] = field(default_factory=lambda: {"POINT": 0.65, "CIRCLE": 1.00, "SLOT": 1.55})

    # --- goalie-driven rebound & cover (base levels shaped by goalie, danger, fatigue, pressure)
    goalie_rebound_base: float = 0.07
    goalie_cover_base: float = 0.29

    # --- goalie pull for 6v5 (regulation only)
    pull_start_seconds_left: int = 180  # 3 minutes
    pull_max_deficit: int = 2

    # --- OT / shootout
    ot_minutes: int = 5
    shootout_rounds: int = 3
    shootout_max_extra_rounds: int = 10  # safety cap


# ============================================================
# 2) SMALL HELPERS
# ============================================================

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


def log_event(cfg: SimConfig, pbp: List[str], clock: int, msg: str) -> None:
    line = f"[{mmss(clock)}] {msg}"
    if cfg.store_pbp:
        pbp.append(line)
    if cfg.verbose:
        print(line)


# ============================================================
# 3) CSV LOADING + UNIT CONSTRUCTION
# ============================================================

def _slot_order_forward(slot: str) -> int:
    s = _key(slot)
    # accept W1/W2/C OR LW/RW/C
    if s in ("c", "center"):
        return 2
    if s in ("w1", "lw", "leftwing", "left_wing"):
        return 1
    if s in ("w2", "rw", "rightwing", "right_wing"):
        return 3
    return 9


def _slot_order_defense(slot: str) -> int:
    s = _key(slot)
    if s in ("ld", "d1", "leftd", "left_defense"):
        return 1
    if s in ("rd", "d2", "rightd", "right_defense"):
        return 2
    return 9


def list_teams_in_skaters_csv(csv_path: str) -> List[str]:
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        fn = {_key(x): x for x in reader.fieldnames}
        if "team" not in fn:
            return []
        teams = set()
        for r in reader:
            t = _norm(r.get(fn["team"], ""))
            if t:
                teams.add(t)
        return sorted(teams)


def load_skaters_for_team(csv_path: str, team_name: str) -> Tuple[List[List[Player]], List[List[Player]]]:
    required = {"team", "name", "position", "unit_type", "unit_no", "slot"}
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Skaters CSV appears to have no header row.")
        fields = [_key(x) for x in reader.fieldnames]
        missing = [k for k in required if k not in fields]
        if missing:
            raise ValueError(f"Skaters CSV missing required columns: {missing}. Found: {reader.fieldnames}")
        rows = list(reader)

    field_map = {_key(fn): fn for fn in (rows[0].keys() if rows else [])}
    rating_cols = [k for k in field_map.keys() if k not in required]

    skaters: List[Player] = []
    for r in rows:
        t = _norm(r.get(field_map["team"], ""))
        if t != team_name:
            continue

        name = _norm(r.get(field_map["name"], ""))
        pos = _norm(r.get(field_map["position"], "F")).upper()
        unit_type = _norm(r.get(field_map["unit_type"], pos)).upper()
        unit_no = _parse_int(r.get(field_map["unit_no"], "0"), default=0)
        slot = _norm(r.get(field_map["slot"], ""))

        ratings: Dict[str, int] = {}
        for k in rating_cols:
            ratings[k] = _parse_int(r.get(field_map[k], ""), default=60)

        skaters.append(
            Player(
                name=name,
                team=t,
                position=pos,
                unit_type=unit_type,
                unit_no=unit_no,
                slot=slot,
                ratings=ratings,
            )
        )

    f = [p for p in skaters if p.unit_type == "F" and p.position == "F"]
    d = [p for p in skaters if p.unit_type == "D" and p.position == "D"]

    f_units: Dict[int, List[Player]] = {}
    d_units: Dict[int, List[Player]] = {}
    for p in f:
        f_units.setdefault(p.unit_no, []).append(p)
    for p in d:
        d_units.setdefault(p.unit_no, []).append(p)

    forwards: List[List[Player]] = []
    for i in range(1, 5):
        unit = sorted(f_units.get(i, []), key=lambda x: _slot_order_forward(x.slot))
        if len(unit) != 3:
            raise ValueError(f"{team_name} forward unit {i} must have 3 players; found {len(unit)}.")
        forwards.append(unit)

    defense: List[List[Player]] = []
    for i in range(1, 4):
        unit = sorted(d_units.get(i, []), key=lambda x: _slot_order_defense(x.slot))
        if len(unit) != 2:
            raise ValueError(f"{team_name} defense unit {i} must have 2 players; found {len(unit)}.")
        defense.append(unit)

    return forwards, defense


def load_goalies_for_team(csv_path: str, team_name: str) -> List[Goalie]:
    """
    Expected goalie CSV columns (case-insensitive):
      team,name,is_starter,(ratings...)
    is_starter can be: 1/0, Y/N, TRUE/FALSE
    If file missing or no goalies for team, defaults will be used.
    """
    try:
        with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError("Goalies CSV appears to have no header row.")
            fields = [_key(x) for x in reader.fieldnames]
            if "team" not in fields or "name" not in fields or "is_starter" not in fields:
                raise ValueError("Goalies CSV must include team,name,is_starter.")
            rows = list(reader)
    except FileNotFoundError:
        return []

    field_map = {_key(fn): fn for fn in (rows[0].keys() if rows else [])}
    required = {"team", "name", "is_starter"}
    rating_cols = [k for k in field_map.keys() if k not in required]

    goalies: List[Goalie] = []
    for r in rows:
        t = _norm(r.get(field_map["team"], ""))
        if t != team_name:
            continue
        name = _norm(r.get(field_map["name"], ""))
        is_starter_raw = _key(r.get(field_map["is_starter"], "0"))
        is_starter = is_starter_raw in ("1", "y", "yes", "true", "t")

        ratings: Dict[str, int] = {}
        for k in rating_cols:
            ratings[k] = _parse_int(r.get(field_map[k], ""), default=60)

        goalies.append(Goalie(name=name, team=t, is_starter=is_starter, ratings=ratings))

    # Ensure starter first, then backup
    goalies.sort(key=lambda g: (not g.is_starter, g.name))
    return goalies[:2]


def build_team(cfg: SimConfig, team_name: str) -> Team:
    forwards, defense = load_skaters_for_team(cfg.skaters_csv_path, team_name)
    goalies = load_goalies_for_team(cfg.goalies_csv_path, team_name)

    if len(goalies) < 2:
        # fallback default goalies (still dynamic via league baseline)
        # ratings keys (optional): reflexes, positioning, rebound_control, puck_tracking, endurance
        g1 = Goalie(name=f"{team_name}-G1", team=team_name, is_starter=True, ratings={"reflexes": 65, "positioning": 65, "rebound_control": 60, "puck_tracking": 65, "endurance": 70})
        g2 = Goalie(name=f"{team_name}-G2", team=team_name, is_starter=False, ratings={"reflexes": 60, "positioning": 60, "rebound_control": 58, "puck_tracking": 60, "endurance": 70})
        goalies = [g1, g2]

    return Team(name=team_name, forwards=forwards, defense=defense, goalies=goalies)


# ============================================================
# 4) PENALTIES / MANPOWER
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
# 5) FACEOFFS / STOPPAGES
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
# 6) PRESSURE
# ============================================================

def update_pressure(state: GameState, dt: int, zone: str, gain_per_sec: float, decay_per_sec: float) -> None:
    if zone == OZ:
        state.oz_pressure = clamp(state.oz_pressure + gain_per_sec * dt, 0.0, 1.0)
    else:
        state.oz_pressure = clamp(state.oz_pressure - decay_per_sec * dt, 0.0, 1.0)


def pressure_spike(state: GameState, spike: float) -> None:
    state.oz_pressure = clamp(state.oz_pressure + spike, 0.0, 1.0)


# ============================================================
# 7) ZONE STEP
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
# 8) RATED PLAYER EVENT SELECTION
# ============================================================

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
# 9) LOCATION-BASED xG + GOALIE MODEL
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
# 10) UTILIZATION + LINE CHANGES (RATINGS + FATIGUE)
# ============================================================

def next_shift_length_seconds(rng: random.Random, shift_min: int, shift_mode: int, shift_max: int) -> int:
    return int(round(rng.triangular(shift_min, shift_max, shift_mode)))


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
        f_fats, cfg.min_weight
    )
    new_d = choose_unit_index(
        rng, d_shares, team.d_pair_toi, time_so_far, cur_d,
        cfg.utilization_strength_d, cfg.repeat_penalty_d, cfg.fatigue_bias_strength_d,
        d_fats, cfg.min_weight
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
# 11) FATIGUE (SKATERS)
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
# 12) TURNOVERS / HITS / PENALTIES (RATING-AWARE)
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
# 13) GOALIE PULL (6v5) REGULATION ONLY
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
# 14) SHOT RESOLUTION (BLOCK/MISS/SAVE/GOAL) + GOALIE PULL END
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
# 15) GOALIE PULL + GOALIE SWITCH LOGIC
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


# ============================================================
# 16) PERIOD SIM (REGULATION / OT)
# ============================================================

def simulate_segment(
    cfg: SimConfig,
    pbp: List[str],
    rng: random.Random,
    home: Team,
    away: Team,
    segment_name: str,
    period_no: int,
    period_length: int,
    sudden_death: bool,
    three_on_three: bool,
    penalties_enabled: bool,
) -> Tuple[List[MinorPenalty], List[MinorPenalty], int, int]:
    """
    Returns (pens_home, pens_away, home_goals_in_segment, away_goals_in_segment)
    """
    step_min = 5
    step_max = 15

    pens_home: List[MinorPenalty] = []
    pens_away: List[MinorPenalty] = []

    state = GameState(
        period=period_no,
        clock=0,
        possession=home,
        zone=NZ,
        home_f_idx=0,
        home_d_idx=0,
        away_f_idx=0,
        away_d_idx=0,
        home_next_change=0,
        away_next_change=0,
        oz_pressure=0.0,
        rebound_window=False,
    )

    state.home_next_change = next_shift_length_seconds(rng, cfg.shift_min, cfg.shift_mode, cfg.shift_max)
    state.away_next_change = next_shift_length_seconds(rng, cfg.shift_min, cfg.shift_mode, cfg.shift_max)

    # Starting manpower
    if three_on_three:
        home_target = 3
        away_target = 3
    else:
        home_target, away_target = manpower_counts(pens_home, pens_away, home.goalie_pulled, away.goalie_pulled)

    home_on = build_on_ice(home, state.home_f_idx, state.home_d_idx, home_target, penalized_id_set(pens_home), rng)
    away_on = build_on_ice(away, state.away_f_idx, state.away_d_idx, away_target, penalized_id_set(pens_away), rng)
    start_shift(home_on)
    start_shift(away_on)

    winner = faceoff(rng, home, away, home_on, away_on)
    state.possession = winner

    log_event(cfg, pbp, state.clock, f"SEGMENT START: {segment_name}")
    log_event(cfg, pbp, state.clock, f"FACEOFF: {winner.name} wins, zone={state.zone}")

    last_clock = 0
    home_goals_seg = 0
    away_goals_seg = 0

    # goalie-switch tracking per period (regulation only)
    home_ga_this_period = 0
    away_ga_this_period = 0

    while state.clock < period_length:
        dt = rng.randint(step_min, step_max)
        state.clock = min(period_length, state.clock + dt)
        elapsed = state.clock - last_clock
        last_clock = state.clock

        # penalties tick (if used)
        tick_penalties(pens_home, elapsed)
        tick_penalties(pens_away, elapsed)
        clear_expired_penalties(pens_home)
        clear_expired_penalties(pens_away)

        # goalie pull arming/execution (REGULATION ONLY: period==3, and not in OT segments)
        if period_length == 20 * 60 and period_no == 3:
            maybe_arm_goalie_pull(cfg, state, home, away, period_length)
            if state.possession is home:
                maybe_execute_goalie_pull(cfg, pbp, state, home)
            else:
                maybe_execute_goalie_pull(cfg, pbp, state, away)

        # manpower
        if three_on_three:
            home_target = 3
            away_target = 3
            home.goalie_pulled = False
            away.goalie_pulled = False
        else:
            home_target, away_target = manpower_counts(pens_home, pens_away, home.goalie_pulled, away.goalie_pulled)

        home_on = build_on_ice(home, state.home_f_idx, state.home_d_idx, home_target, penalized_id_set(pens_home), rng)
        away_on = build_on_ice(away, state.away_f_idx, state.away_d_idx, away_target, penalized_id_set(pens_away), rng)

        add_toi(home_on, elapsed)
        add_toi(away_on, elapsed)

        # only record unit utilization in true 5v5 regulation
        if (period_length == 20 * 60) and (home_target == 5 and away_target == 5):
            home.f_line_toi[state.home_f_idx] += elapsed
            home.d_pair_toi[state.home_d_idx] += elapsed
            away.f_line_toi[state.away_f_idx] += elapsed
            away.d_pair_toi[state.away_d_idx] += elapsed

        # skater fatigue
        on_ids = {id(p) for p in home_on + away_on}
        update_player_fatigue(
            all_players=team_all_players(home) + team_all_players(away),
            on_ice_ids=on_ids,
            dt=elapsed,
            base_gain_per_sec=cfg.fat_gain_base,
            base_recover_per_sec=cfg.fat_recover_base,
            endurance_gain_scale=cfg.endurance_gain_scale,
            endurance_recover_scale=cfg.endurance_recover_scale,
        )

        # pressure update
        attacking = state.possession
        defending = other_team(attacking, home, away)

        pens_att = pens_home if attacking is home else pens_away
        pens_def = pens_away if attacking is home else pens_home

        pp_bonus, pk_bonus = special_teams_bonuses(
            pens_att, pens_def,
            att_pulled=attacking.goalie_pulled,
            def_pulled=defending.goalie_pulled
        )

        eff_pressure_gain = cfg.pressure_gain_per_sec * (1.0 + cfg.pp_pressure_gain_bonus * pp_bonus)
        update_pressure(state, elapsed, state.zone, eff_pressure_gain, cfg.pressure_decay_per_sec)

        # line changes
        if state.clock >= state.home_next_change:
            apply_line_change(cfg, pbp, rng, home, True, state, state.clock, period_length, home_target, away_target)
            state.home_next_change = state.clock + next_shift_length_seconds(rng, cfg.shift_min, cfg.shift_mode, cfg.shift_max)

        if state.clock >= state.away_next_change:
            apply_line_change(cfg, pbp, rng, away, False, state, state.clock, period_length, away_target, home_target)
            state.away_next_change = state.clock + next_shift_length_seconds(rng, cfg.shift_min, cfg.shift_mode, cfg.shift_max)

        # effective probabilities
        eff_turnover = clamp(cfg.base_turnover_prob * (1.0 + 0.18 * state.oz_pressure), 0.01, 0.75)
        eff_turnover *= (1.0 - 0.18 * pp_bonus) * (1.0 + 0.20 * pk_bonus)
        eff_turnover = clamp(eff_turnover, 0.01, 0.85)

        eff_shot_attempt = clamp(cfg.base_shot_attempt_prob * (1.0 + cfg.pressure_shot_attempt_up * state.oz_pressure), 0.01, 0.99)
        eff_shot_attempt *= (1.0 + cfg.pp_shot_attempt_bonus * pp_bonus)

        eff_on_goal_base = clamp(cfg.base_on_goal_prob * (1.0 + cfg.pp_on_goal_bonus * pp_bonus), 0.05, 0.99)
        eff_block_base = clamp(cfg.base_shot_blocked_prob * (1.0 + 0.25 * pk_bonus), 0.01, 0.85)

        # stoppages
        if state.zone == DZ and rng.random() < cfg.icing_prob_in_dz:
            do_stoppage(cfg, pbp, rng, home, away, state, "icing", DZ, home_on, away_on)
            continue

        if rng.random() < stoppage_probability_by_zone(state.zone):
            stype = pick_misc_stoppage_type(rng)
            fzone = state.zone if rng.random() < cfg.misc_faceoff_same_zone_prob else NZ
            do_stoppage(cfg, pbp, rng, home, away, state, stype, fzone, home_on, away_on)
            continue

        # turnovers
        if rng.random() < eff_turnover:
            penalty_called = resolve_turnover_event(
                cfg, pbp, rng, home, away, state,
                enable_penalties=penalties_enabled,
                pens_home=pens_home,
                pens_away=pens_away,
                home_on=home_on,
                away_on=away_on,
                pp_bonus=pp_bonus,
                pk_bonus=pk_bonus,
            )
            if penalty_called:
                do_stoppage(cfg, pbp, rng, home, away, state, "penalty", NZ, home_on, away_on)
                continue
            state.zone = NZ
            continue

        # zone movement + offside
        new_zone, offside, entered_oz = step_zone_with_offside_check(
            rng, state.zone, cfg.offside_prob_on_entry, cfg.dz_to_nz_prob, cfg.nz_to_oz_prob, cfg.oz_hold_prob
        )
        state.zone = new_zone
        if offside:
            do_stoppage(cfg, pbp, rng, home, away, state, "offside", NZ, home_on, away_on)
            continue

        # OZ clear attempt
        if maybe_oz_clear_attempt(cfg, pbp, rng, home, away, state, pk_bonus, home_on, away_on):
            continue

        # SHOTS only in OZ
        if state.zone == OZ and rng.random() < eff_shot_attempt:
            attacking_team = state.possession
            defending_team = other_team(attacking_team, home, away)

            attackers = home_on if attacking_team is home else away_on
            defenders = away_on if attacking_team is home else home_on

            shooter = pick_shooter(rng, attackers)
            shooter.shot_attempts += 1
            attacking_team.shot_attempts += 1
            pressure_spike(state, cfg.pressure_spike_on_attempt)

            loc = choose_shot_location(rng, cfg.loc_weights)

            rb = " RB" if state.rebound_window else ""
            log_event(cfg, pbp, state.clock, f"SHOT ATTEMPT {attacking_team.name} by {shooter.name}{rb} loc={loc} (pressure={state.oz_pressure:.2f})")

            # BLOCK check
            blocker = pick_blocker(rng, defenders)
            blk = r01_player(blocker, "shot_blocking", 60)
            da = r01_player(blocker, "defensive_awareness", 60)
            oa = r01_player(shooter, "offensive_awareness", 60)
            shooter_tired = 1.0 - fatigue_multiplier(shooter)

            eff_block = eff_block_base
            eff_block += 0.10 * (blk - 0.55) + 0.06 * (da - 0.55) - 0.06 * (oa - 0.55)
            eff_block += 0.06 * shooter_tired
            eff_block = clamp(eff_block, 0.05, 0.55)

            if rng.random() < eff_block:
                blocker.blocks += 1
                defending_team.shots_blocked_against += 1
                log_event(cfg, pbp, state.clock, f"BLOCKED by {blocker.name}")
                resolve_blocked_attempt(cfg, pbp, rng, home, away, state)
                continue

            # ON GOAL check
            acc = r01_player(shooter, "shooting_accuracy", 60)
            on_goal = eff_on_goal_base * (0.80 + 0.50 * acc) * (0.85 + 0.20 * fatigue_multiplier(shooter))
            on_goal = clamp(on_goal, 0.05, 0.98)

            if rng.random() >= on_goal:
                log_event(cfg, pbp, state.clock, f"MISS by {shooter.name} (no SOG)")
                resolve_missed_attempt(cfg, pbp, rng, home, away, state, home_on, away_on)
                continue

            # Shot on goal
            shooter.shots += 1
            attacking_team.shots += 1
            pressure_spike(state, cfg.pressure_spike_on_sog)

            xg = shot_quality_xg(cfg, shooter, state, pp_bonus, pk_bonus, loc)
            shooter.xg += xg
            attacking_team.xg += xg

            # pick goalie (starter or backup if switched)
            g = current_goalie(defending_team)
            g.shots_against += 1

            def_team_fat = avg_fatigue(defenders)
            save_ch = goalie_save_chance(cfg, g, xg, state.oz_pressure, def_team_fat, loc)
            # equivalently goal chance = 1 - save_ch
            goal_prob = clamp(1.0 - save_ch, 0.005, 0.80)

            log_event(cfg, pbp, state.clock, f"SHOT ON GOAL by {shooter.name} xG={xg:.3f} goalP={goal_prob:.3f} vs {g.name}")

            # consume rebound window
            state.rebound_window = False

            # resolve goal/save
            if rng.random() < goal_prob:
                # goal
                attacking_team.goals += 1
                if attacking_team is home:
                    home_goals_seg += 1
                    away_ga_this_period += 1
                else:
                    away_goals_seg += 1
                    home_ga_this_period += 1

                shooter.goals += 1
                assists = maybe_assists(rng, shooter, attackers)
                for a in assists:
                    a.assists += 1

                g.goals_against += 1
                update_goalie_state_on_shot(g, saved=False, xg=xg, dt=elapsed)

                log_event(cfg, pbp, state.clock, f"GOAL {attacking_team.name}! scorer={shooter.name} assists={[a.name for a in assists]} "
                                                f"(score {away.name} {away.goals} - {home.name} {home.goals})")

                # PP goal ends a minor immediately
                if pp_bonus > 0.0:
                    attacking_team.pp_goals += 1
                    ended = end_one_minor_on_pp_goal(pens_def)
                    if ended:
                        log_event(cfg, pbp, state.clock, f"PP GOAL ends penalty: {defending_team.name} {ended.penalty_type}")

                # any goal ends goalie pull immediately
                home.goalie_pulled = False
                away.goalie_pulled = False
                state.home_pull_armed = False
                state.away_pull_armed = False

                # goalie switch checks (regulation only)
                if period_length == 20 * 60:
                    if defending_team is home:
                        maybe_switch_goalie(home, period_no, home_ga_this_period, home, away, cfg, pbp, state.clock)
                    else:
                        maybe_switch_goalie(away, period_no, away_ga_this_period, home, away, cfg, pbp, state.clock)

                if sudden_death:
                    do_stoppage(cfg, pbp, rng, home, away, state, "after goal (sudden death ends)", NZ, home_on, away_on)
                    return pens_home, pens_away, home_goals_seg, away_goals_seg

                do_stoppage(cfg, pbp, rng, home, away, state, "after goal", NZ, home_on, away_on)
                continue

            # save
            g.saves += 1
            update_goalie_state_on_shot(g, saved=True, xg=xg, dt=elapsed)
            resolve_save_outcome(cfg, pbp, rng, home, away, state, attacking_team, defending_team, g, xg, loc, home_on, away_on)
            continue

    log_event(cfg, pbp, state.clock, f"SEGMENT END: {segment_name}")
    return pens_home, pens_away, home_goals_seg, away_goals_seg


# ============================================================
# 17) SHOOTOUT (NO SKATER/GOALIE STATS CREDITED)
# ============================================================

def shootout(cfg: SimConfig, pbp: List[str], rng: random.Random, home: Team, away: Team) -> Tuple[str, List[ShootoutAttempt]]:
    log: List[ShootoutAttempt] = []
    home_score = 0
    away_score = 0

    def pick_shooter_team(team: Team, used: set) -> Player:
        pool = [p for p in team_all_players(team) if p.position == "F"]
        # weight toward shooters
        def w(p: Player) -> float:
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

    def attempt(shooter_team: Team, goalie_team: Team, shooter: Player, goalie: Goalie) -> bool:
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


# ============================================================
# 18) GAME WRAPPER (REG + OT + SO)
# ============================================================

def simulate_game_once(cfg: SimConfig, rng: random.Random, home: Team, away: Team) -> GameResult:
    pbp: List[str] = []

    home.reset_game_state()
    away.reset_game_state()

    home_goals_by_period = [0, 0, 0]
    away_goals_by_period = [0, 0, 0]

    # Regulation
    for p in range(1, 4):
        _, _, hg, ag = simulate_segment(
            cfg=cfg, pbp=pbp, rng=rng,
            home=home, away=away,
            segment_name=f"Period {p}",
            period_no=p, period_length=20 * 60,
            sudden_death=False,
            three_on_three=False,
            penalties_enabled=cfg.enable_penalties_regulation,
        )
        home_goals_by_period[p - 1] = hg
        away_goals_by_period[p - 1] = ag

    went_to_ot = False
    ot_winner = None
    went_to_so = False
    so_winner = None
    shootout_log: List[ShootoutAttempt] = []

    # OT (5 min 3v3 sudden death), NO penalties, NO goalie pulls
    if home.goals == away.goals:
        went_to_ot = True
        home.goalie_pulled = False
        away.goalie_pulled = False

        _, _, hg, ag = simulate_segment(
            cfg=cfg, pbp=pbp, rng=rng,
            home=home, away=away,
            segment_name=f"Overtime ({cfg.ot_minutes} min, 3v3)",
            period_no=4, period_length=cfg.ot_minutes * 60,
            sudden_death=True,
            three_on_three=True,
            penalties_enabled=cfg.enable_penalties_ot,  # decision: no OT penalties
        )
        if hg > 0:
            ot_winner = home.name
        elif ag > 0:
            ot_winner = away.name

    # Shootout if still tied
    if home.goals == away.goals:
        went_to_so = True
        winner, so_log = shootout(cfg, pbp, rng, home, away)
        so_winner = winner
        shootout_log = so_log

        # award the game-winning “result goal” to team score only (not skaters/goalies)
        if winner == home.name:
            home.goals += 1
        else:
            away.goals += 1

    # Build report-friendly tables
    team_summary = {
        away.name: {
            "Goals": away.goals,
            "xG": round(away.xg, 2),
            "SOG": away.shots,
            "Att": away.shot_attempts,
            "SB-against": away.shots_blocked_against,
            "GV": away.giveaways,
            "TK": away.takeaways,
            "HIT": away.hits,
            "PP": f"{away.pp_goals}/{away.pp_opportunities}",
            "FO": f"{away.team_faceoff_wins}-{away.team_faceoff_losses}",
        },
        home.name: {
            "Goals": home.goals,
            "xG": round(home.xg, 2),
            "SOG": home.shots,
            "Att": home.shot_attempts,
            "SB-against": home.shots_blocked_against,
            "GV": home.giveaways,
            "TK": home.takeaways,
            "HIT": home.hits,
            "PP": f"{home.pp_goals}/{home.pp_opportunities}",
            "FO": f"{home.team_faceoff_wins}-{home.team_faceoff_losses}",
        },
    }

    def skater_rows(team: Team) -> List[Dict[str, Any]]:
        rows = []
        for p in team_all_players(team):
            rows.append({
                "Player": p.name,
                "Pos": p.position,
                "Unit": f"{p.unit_type}{p.unit_no}",
                "G": p.goals,
                "A": p.assists,
                "xG": round(p.xg, 2),
                "Att": p.shot_attempts,
                "SOG": p.shots,
                "BLK": p.blocks,
                "GV": p.giveaways,
                "TK": p.takeaways,
                "HIT": p.hits,
                "PIM": p.pim,
                "FO": f"{p.faceoff_wins}-{p.faceoff_losses}",
                "TOI": fmt_toi(p.toi_seconds),
            })
        return rows

    def goalie_rows(team: Team) -> List[Dict[str, Any]]:
        rows = []
        for g in team.goalies:
            rows.append({
                "Goalie": g.name,
                "Role": "Starter" if g.is_starter else "Backup",
                "GA": g.goals_against,
                "SA": g.shots_against,
                "SV": g.saves,
                "SV%": (0.0 if g.shots_against <= 0 else round(g.saves / g.shots_against, 3)),
                "REB": g.rebounds_allowed,
                "COV": g.covers,
                "Fat": round(g.fatigue, 1),
                "Conf": round(g.confidence, 2),
                "TOI": fmt_toi(g.toi_seconds),
            })
        return rows

    result = GameResult(
        home=home.name,
        away=away.name,
        home_goals=home.goals,
        away_goals=away.goals,
        home_goals_by_period=home_goals_by_period,
        away_goals_by_period=away_goals_by_period,
        went_to_ot=went_to_ot,
        ot_winner=ot_winner,
        went_to_so=went_to_so,
        so_winner=so_winner,
        shootout_log=shootout_log,
        team_summary=team_summary,
        skaters={away.name: skater_rows(away), home.name: skater_rows(home)},
        goalies={away.name: goalie_rows(away), home.name: goalie_rows(home)},
        pbp=pbp if cfg.store_pbp else [],
    )
    return result


# ============================================================
# 19) REPORT PRINTING
# ============================================================

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
        header = f"{'Player':18} {'Pos':>3} {'Unit':>4} {'G':>3} {'A':>3} {'xG':>6} {'Att':>4} {'SOG':>4} {'BLK':>4} {'GV':>4} {'TK':>4} {'HIT':>4} {'PIM':>4} {'FO':>7} {'TOI':>6}"
        print(header)
        for r in gr.skaters[team_name]:
            print(
                f"{r['Player'][:18]:18} {r['Pos']:>3} {r['Unit']:>4} {r['G']:>3} {r['A']:>3} {r['xG']:>6.2f} "
                f"{r['Att']:>4} {r['SOG']:>4} {r['BLK']:>4} {r['GV']:>4} {r['TK']:>4} {r['HIT']:>4} {r['PIM']:>4} "
                f"{r['FO']:>7} {r['TOI']:>6}"
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


# ============================================================
# 20) SERIES (BEST OF N / UP TO 100)
# ============================================================

@dataclass
class SeriesResult:
    home: str
    away: str
    games: int
    home_wins: int
    away_wins: int
    ties: int  # should be 0 because OT+SO resolves, but kept for safety

    avg: Dict[str, Dict[str, float]] = field(default_factory=dict)
    game_results: List[GameResult] = field(default_factory=list)


def run_series(cfg: SimConfig, home: Team, away: Team, games: int, seed: Optional[int] = None) -> SeriesResult:
    games = max(1, min(cfg.max_games, int(games)))
    rng = random.Random(seed)

    home_wins = away_wins = ties = 0

    # aggregates for report-friendly stats
    agg = {
        home.name: {"Goals": 0, "xG": 0.0, "SOG": 0, "Att": 0, "GV": 0, "TK": 0, "HIT": 0, "PPG": 0, "PPO": 0},
        away.name: {"Goals": 0, "xG": 0.0, "SOG": 0, "Att": 0, "GV": 0, "TK": 0, "HIT": 0, "PPG": 0, "PPO": 0},
    }

    results: List[GameResult] = []

    # For series runs, default to not printing pbp unless user requests it in menu
    # (we leave cfg as-is; menu will set verbose/store_pbp)
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

    avg = {}
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


# ============================================================
# 21) TERMINAL MENU (SIMPLE)
# ============================================================

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


def prompt_team_choice(teams: List[str], label: str, default_idx: int = 0) -> str:
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

    seed = None
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


if __name__ == "__main__":
    main()
