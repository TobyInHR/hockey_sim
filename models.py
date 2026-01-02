from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DZ = "DZ"
NZ = "NZ"
OZ = "OZ"


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
    shift_seconds_current: int = 0
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
                p.shift_seconds_current = 0
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
                p.shift_seconds_current = 0
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
    home_shift_target: int = 0
    away_shift_target: int = 0

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
class SeriesResult:
    home: str
    away: str
    games: int
    home_wins: int
    away_wins: int
    ties: int  # should be 0 because OT+SO resolves, but kept for safety

    avg: Dict[str, Dict[str, float]] = field(default_factory=dict)
    game_results: List[GameResult] = field(default_factory=list)
