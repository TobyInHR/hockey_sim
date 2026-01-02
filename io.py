import csv
from typing import Dict, List, Tuple

from .config import SimConfig
from .models import Player, Goalie, Team
from .utils import _key, _norm, _parse_int


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
        g1 = Goalie(
            name=f"{team_name}-G1",
            team=team_name,
            is_starter=True,
            ratings={"reflexes": 65, "positioning": 65, "rebound_control": 60, "puck_tracking": 65, "endurance": 70},
        )
        g2 = Goalie(
            name=f"{team_name}-G2",
            team=team_name,
            is_starter=False,
            ratings={"reflexes": 60, "positioning": 60, "rebound_control": 58, "puck_tracking": 60, "endurance": 70},
        )
        goalies = [g1, g2]

    return Team(name=team_name, forwards=forwards, defense=defense, goalies=goalies)
