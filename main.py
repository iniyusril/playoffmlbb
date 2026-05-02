"""
FastAPI server – MPL ID S17 Playoff Probability Tracker
"""

import asyncio
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from scraper import scrape_data
from simulator import run_simulation, compute_best_worst

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MPL ID Playoff Probability", version="1.0.0")

# ── In-memory cache ───────────────────────────────────────────────────────────
CACHE_TTL = 1800  # 30 menit

_cache: dict = {
    "data":      None,
    "timestamp": 0.0,
    "lock":      None,        # asyncio.Lock – dibuat saat startup
}


@app.on_event("startup")
async def startup():
    _cache["lock"] = asyncio.Lock()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "templates" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html tidak ditemukan")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/data")
async def get_data():
    """
    Mengembalikan standings, remaining matches, dan playoff probability.
    Hasil di-cache selama 10 menit.
    """
    async with _cache["lock"]:
        now = time.time()
        is_cached = (
            _cache["data"] is not None
            and (now - _cache["timestamp"]) < CACHE_TTL
        )

        if not is_cached:
            try:
                logger.info("Cache expired atau kosong – memulai scraping...")
                scraped = await scrape_data()
                standings = scraped["standings"]
                remaining = scraped["remaining_matches"]

                probabilities = run_simulation(standings, remaining)
                best_worst = compute_best_worst(standings, remaining)

                # Gabungkan standings dengan probabilitas
                standings_list = _build_standings_list(standings, probabilities, best_worst)

                _cache["data"] = {
                    "standings":         standings_list,
                    "remaining_matches": [list(m) for m in remaining],
                    "total_remaining":   len(remaining),
                    "last_updated":      now,
                    "is_cached":         False,
                }
                _cache["timestamp"] = now
                logger.info("Cache diperbarui. %d tim, %d match tersisa.", len(standings), len(remaining))

            except Exception as exc:
                logger.error("Scraping gagal: %s", exc, exc_info=True)
                if _cache["data"] is not None:
                    # Kembalikan data lama yang masih ada
                    _cache["data"]["is_cached"] = True
                    return JSONResponse(_cache["data"])
                raise HTTPException(status_code=503, detail=f"Gagal mengambil data: {exc}")
        else:
            _cache["data"]["is_cached"] = True

    return JSONResponse(_cache["data"])


@app.post("/api/refresh")
async def force_refresh():
    """
    Paksa refresh cache (bypass TTL).
    Berguna saat pertandingan baru saja selesai.
    """
    async with _cache["lock"]:
        _cache["timestamp"] = 0.0  # Expire cache sekarang

    return JSONResponse({"status": "ok", "message": "Cache akan diperbarui pada request berikutnya."})


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_standings_list(standings: dict, probabilities: dict, best_worst: dict) -> list:
    """
    Urutkan tim berdasarkan standings saat ini dan gabungkan dengan probabilitas playoff.
    """
    from simulator import _sort_key

    sorted_teams = sorted(standings.values(), key=_sort_key)

    result = []
    for rank, team_data in enumerate(sorted_teams, start=1):
        name = team_data["name"]
        prob = probabilities.get(name, 0.0)
        bw   = best_worst.get(name, {})

        # Gunakan probabilitas untuk status (threshold lebih reliable dari best/worst rank approx)
        best_rank  = bw.get("best_rank", rank)
        worst_rank = bw.get("worst_rank", rank)

        if prob >= 99.0:
            status = "PASTI_LOLOS"
        elif prob <= 1.0:
            status = "ELIMINASI"
        else:
            status = "BERSAING"

        result.append({
            "rank":          rank,
            "name":          name,
            "match_points":  team_data["match_points"],
            "wins":          team_data["wins"],
            "losses":        team_data["losses"],
            "net_game_win":  team_data["net_game_win"],
            "game_wins":     team_data["game_wins"],
            "game_losses":   team_data["game_losses"],
            "logo":          team_data["logo"],
            "color":         team_data["color"],
            "playoff_prob":  prob,
            "best_rank":     best_rank,
            "worst_rank":    worst_rank,
            "status":        status,
        })

    return result
