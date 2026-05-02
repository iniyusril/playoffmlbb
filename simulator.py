"""
Monte Carlo Simulation untuk menghitung persentase peluang tiap tim
lolos ke babak playoff MPL ID Season 17.

Logika:
  - 9 tim, top 6 lolos playoff
  - Setiap pertandingan sisa: 50/50 peluang menang
  - Score BO3: ~55% kemungkinan 2-0, ~45% kemungkinan 2-1
  - Tiebreaker: Match Points → Net Game Win → Game Win Rate
  - N=10.000 iterasi
"""

import random
from copy import deepcopy

PLAYOFF_SPOTS = 6
N_SIMULATIONS = 10_000

# Peluang skor 2-0 vs 2-1 dalam BO3 (berdasarkan statistik rata-rata MPL)
PROB_2_0 = 0.55


def run_simulation(standings: dict, remaining_matches: list, n: int = N_SIMULATIONS) -> dict:
    """
    Jalankan Monte Carlo simulation.

    Args:
        standings: dict { team_code: { match_points, wins, losses,
                                       net_game_win, game_wins, game_losses } }
        remaining_matches: list of (team1, team2) tuples (pertandingan belum dimainkan)
        n: jumlah iterasi simulasi

    Returns:
        dict { team_code: probability_percent (float) }
    """
    if not standings:
        return {}

    # Validasi: hanya proses tim yang ada di standings
    valid_teams = set(standings.keys())
    valid_matches = [
        (t1, t2) for t1, t2 in remaining_matches
        if t1 in valid_teams and t2 in valid_teams
    ]

    playoff_count: dict = {team: 0 for team in standings}

    for _ in range(n):
        sim = deepcopy(standings)

        for t1, t2 in valid_matches:
            winner = random.choice([t1, t2])
            loser  = t2 if winner == t1 else t1

            # Simulasi score BO3
            if random.random() < PROB_2_0:
                # 2-0: winner +2 gw, loser +2 gl
                _apply_result(sim, winner, loser, gw=2, gl=0)
            else:
                # 2-1: winner 2gw/1gl, loser 1gw/2gl
                _apply_result(sim, winner, loser, gw=2, gl=1)

        # Sorting berdasarkan tiebreaker MPL ID
        sorted_teams = sorted(
            sim.keys(),
            key=lambda t: _sort_key(sim[t]),
        )

        for team in sorted_teams[:PLAYOFF_SPOTS]:
            playoff_count[team] += 1

    return {
        team: round(count / n * 100, 1)
        for team, count in playoff_count.items()
    }


def compute_best_worst(standings: dict, remaining_matches: list) -> dict:
    """
    Hitung peluang terbaik (best case) dan terburuk (worst case) tiap tim.
    Berguna untuk badge 'Pasti Lolos' dan 'Pasti Gugur'.

    Returns:
        dict { team: { best_rank: int, worst_rank: int } }
    """
    if not standings:
        return {}

    valid_teams = set(standings.keys())
    valid_matches = [
        (t1, t2) for t1, t2 in remaining_matches
        if t1 in valid_teams and t2 in valid_teams
    ]

    result = {team: {"best_rank": None, "worst_rank": None} for team in standings}

    # Iterasi penuh terbatas: hanya cek scenario menang semua / kalah semua
    for focus_team in standings:
        # Skenario terbaik: focus_team menang semua, lawan best case lainnya
        sim_best = deepcopy(standings)
        for t1, t2 in valid_matches:
            if focus_team in (t1, t2):
                winner = focus_team
                loser  = t2 if winner == t1 else t1
            else:
                # Lawan focus_team menang juga (worst case untuk focus_team di luar match-nya)
                winner = t1
                loser  = t2
            _apply_result(sim_best, winner, loser, gw=2, gl=0)

        sorted_best = sorted(sim_best.keys(), key=lambda t: _sort_key(sim_best[t]))
        result[focus_team]["best_rank"] = sorted_best.index(focus_team) + 1

        # Skenario terburuk: focus_team kalah semua
        sim_worst = deepcopy(standings)
        for t1, t2 in valid_matches:
            if focus_team in (t1, t2):
                loser  = focus_team
                winner = t2 if loser == t1 else t1
            else:
                winner = t1
                loser  = t2
            _apply_result(sim_worst, winner, loser, gw=2, gl=0)

        sorted_worst = sorted(sim_worst.keys(), key=lambda t: _sort_key(sim_worst[t]))
        result[focus_team]["worst_rank"] = sorted_worst.index(focus_team) + 1

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_result(sim: dict, winner: str, loser: str, gw: int, gl: int) -> None:
    """Update standings dict setelah satu pertandingan BO3."""
    sim[winner]["wins"]          += 1
    sim[winner]["match_points"]  += 1
    sim[winner]["game_wins"]     += gw
    sim[winner]["game_losses"]   += gl
    sim[winner]["net_game_win"]  += gw - gl

    sim[loser]["losses"]         += 1
    sim[loser]["game_wins"]      += gl
    sim[loser]["game_losses"]    += gw
    sim[loser]["net_game_win"]   += gl - gw


def _sort_key(team_data: dict) -> tuple:
    """
    Tiebreaker MPL ID:
    1. Match Points (desc)
    2. Net Game Win (desc)
    3. Game Win Rate (desc)
    """
    total_games = team_data["game_wins"] + team_data["game_losses"]
    gwr = team_data["game_wins"] / total_games if total_games > 0 else 0.0
    return (
        -team_data["match_points"],
        -team_data["net_game_win"],
        -gwr,
    )
