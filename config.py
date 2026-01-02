from dataclasses import dataclass, field
from typing import Dict, List, Tuple


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
    shift_endurance_weight: float = 0.25
    shift_late_game_minute: int = 35
    shift_trailing_longer_mult: float = 1.05
    shift_leading_shorter_mult: float = 0.95
    shift_pressure_push_mult: float = 1.10
    shift_pressure_relief_mult: float = 0.92
    caught_on_pressure_threshold: float = 0.70
    caught_on_chance: float = 0.12
    caught_on_extension_mult: float = 1.35
    stoppage_change_ready_fraction: float = 0.65
    rolling_change_ready_fraction: float = 0.55
    dz_low_pressure_change_threshold: float = 0.22
    toi_guardrails_f: List[Tuple[int, int]] = field(default_factory=lambda: [(1100, 1560), (900, 1320), (720, 1080), (480, 660)])
    toi_guardrails_d: List[Tuple[int, int]] = field(default_factory=lambda: [(1380, 1560), (1200, 1380), (900, 1140)])

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
