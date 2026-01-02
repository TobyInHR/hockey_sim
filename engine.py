import random
from typing import Any, Dict, List, Optional, Tuple

from .config import SimConfig
from .models import DZ, NZ, OZ, GameResult, GameState, MinorPenalty, Player, Team

# Gameplay module: only import names that are actually defined in gameplay.py
from .gameplay import (
    apply_line_change,
    build_on_ice,
    choose_shot_location,
    clear_expired_penalties,
    current_goalie,
    do_stoppage,
    end_goalie_pull_on_possession_loss,
    end_one_minor_on_pp_goal,
    faceoff,
    manpower_counts,
    maybe_arm_goalie_pull,
    maybe_assists,
    maybe_execute_goalie_pull,
    maybe_oz_clear_attempt,
    maybe_switch_goalie,
    next_shift_length_seconds,
    penalized_id_set,
    pick_blocker,
    pick_misc_stoppage_type,
    pick_shooter,
    pressure_spike,
    resolve_blocked_attempt,
    resolve_missed_attempt,
    resolve_save_outcome,
    resolve_turnover_event,
    shot_quality_xg,
    special_teams_bonuses,
    step_zone_with_offside_check,
    stoppage_probability_by_zone,
    tick_penalties,
    update_goalie_state_on_shot,
    update_player_fatigue,
    update_pressure,
)

from .shootout import shootout

# Utils module: helpers live here (this is what was causing your ImportError)
from .utils import (
    add_toi,
    avg_fatigue,
    clamp,
    fatigue_multiplier,
    fmt_toi,
    log_event,
    other_team,
    r01_player,
    team_all_players,
)

# Alias to match the original name used in engine without renaming the gameplay function
from .gameplay import goalie_save_chance as g_save_chance


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

    # shift counter on start
    for p in home_on:
        p.shifts += 1
    for p in away_on:
        p.shifts += 1

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

            # goalie
            g = current_goalie(defending_team)
            g.shots_against += 1

            def_team_fat = avg_fatigue(defenders)
            save_ch = g_save_chance(cfg, g, xg, state.oz_pressure, def_team_fat, loc)
            goal_prob = clamp(1.0 - save_ch, 0.005, 0.80)

            log_event(cfg, pbp, state.clock, f"SHOT ON GOAL by {shooter.name} xG={xg:.3f} goalP={goal_prob:.3f} vs {g.name}")

            state.rebound_window = False

            # resolve goal/save
            if rng.random() < goal_prob:
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

                log_event(
                    cfg, pbp, state.clock,
                    f"GOAL {attacking_team.name}! scorer={shooter.name} assists={[a.name for a in assists]} "
                    f"(score {away.name} {away.goals} - {home.name} {home.goals})"
                )

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
    shootout_log = []

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
            penalties_enabled=cfg.enable_penalties_ot,
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

    def skater_rows(team: Team):
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

    def goalie_rows(team: Team):
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

    return GameResult(
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
