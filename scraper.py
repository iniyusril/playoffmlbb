"""
Scraper untuk id-mpl.com menggunakan Playwright (headless Chromium).
Mengambil standings dan jadwal pertandingan yang belum dimainkan.
"""

import re
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

TEAM_CODES = ["ONIC", "DEWA", "BTR", "AE", "EVOS", "TLID", "GEEK", "NAVI", "RRQ"]

TEAM_LOGOS = {
    "ONIC": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/onic-64.png",
    "DEWA": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/dewa-64.png",
    "BTR":  "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/btr-64.png",
    "AE":   "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/ae-64.png",
    "EVOS": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/evos-64.png",
    "TLID": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/tlid-64.png",
    "GEEK": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/geek-64.png",
    "NAVI": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/navi-64.png",
    "RRQ":  "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/rrq-64.png",
}

TEAM_COLORS = {
    "ONIC": "#E8871A",
    "DEWA": "#8B0000",
    "BTR":  "#E63946",
    "AE":   "#00B4D8",
    "EVOS": "#FF0000",
    "TLID": "#009EBD",
    "GEEK": "#9B59B6",
    "NAVI": "#F1C40F",
    "RRQ":  "#CC0033",
}


async def scrape_data() -> dict:
    """
    Scrape standings dan remaining matches dari id-mpl.com.
    Returns dict: { standings: dict, remaining_matches: list[tuple] }
    """
    logger.info("Memulai scraping id-mpl.com ...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)

        # ── 1. Standings dari halaman utama ──────────────────────────────
        await page.goto("https://id-mpl.com/", wait_until="domcontentloaded")

        # Tunggu sampai data standings muncul (RRQ adalah tim terakhir di tabel)
        try:
            await page.wait_for_function(
                "() => document.body.textContent.includes('RRQ')",
                timeout=15_000,
            )
        except Exception:
            logger.warning("Timeout menunggu standings penuh, lanjut dengan konten tersedia.")

        # Scroll ke bawah supaya lazy-loaded content ter-render
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1_500)

        # Gunakan textContent (bukan innerText) agar element tersembunyi ikut terbaca
        home_text: str = await page.evaluate("() => document.body.textContent")
        logger.info("Home page fetched, panjang text: %d", len(home_text))

        standings = parse_standings(home_text)
        logger.info("Standings ditemukan: %s", list(standings.keys()))

        # ── 2. Schedule dari halaman jadwal ──────────────────────────────
        await page.goto("https://id-mpl.com/schedule", wait_until="domcontentloaded")

        # Tunggu match cards muncul di DOM
        try:
            await page.wait_for_selector(".match.position-relative", timeout=15_000)
        except Exception:
            logger.warning("Match elements tidak ditemukan, lanjut.")

        await page.wait_for_timeout(1_500)

        # Ekstrak langsung dari DOM — lebih andal daripada textContent parsing.
        # Halaman menampilkan match yang sama di beberapa filter-view (per tim),
        # sehingga deduplication via sorted key wajib.
        remaining = await _dom_extract_remaining_matches(page)
        logger.info("Remaining matches dari DOM: %d pertandingan", len(remaining))

        await browser.close()

    # Fallback: tambah match yang diketahui jika DOM extraction kurang lengkap
    fallback_list = _fallback_remaining_matches()
    seen = {frozenset(m) for m in remaining}
    for m in fallback_list:
        if frozenset(m) not in seen:
            remaining.append(m)
            seen.add(frozenset(m))

    logger.info("Total remaining matches setelah merge fallback: %d", len(remaining))
    return {"standings": standings, "remaining_matches": remaining}


async def _dom_extract_remaining_matches(page) -> list:
    """
    Ekstrak pertandingan yang belum dimainkan langsung dari DOM
    menggunakan selector .match.position-relative.

    Setiap pertandingan ditampilkan di beberapa konteks filter (per tim),
    sehingga deduplikasi via sorted-pair key wajib.
    """
    _JS = """
() => {
    var VALID_TEAMS = ["ONIC","DEWA","BTR","AE","EVOS","TLID","GEEK","NAVI","RRQ"];
    var seen = {};
    var results = [];
    var matchEls = document.querySelectorAll('.match.position-relative');

    for (var i = 0; i < matchEls.length; i++) {
        var el = matchEls[i];

        var teamEls = el.querySelectorAll('.match-team');
        var teams = [];
        for (var j = 0; j < teamEls.length; j++) {
            var t = teamEls[j].textContent.trim();
            if (VALID_TEAMS.indexOf(t) !== -1) teams.push(t);
        }
        if (teams.length !== 2) continue;

        var hasReplay = !!el.querySelector('a[href*="youtube"]') ||
                        !!el.querySelector('[class*="replay"]') ||
                        el.textContent.toLowerCase().indexOf('details') !== -1;
        if (hasReplay) continue;

        var key = [teams[0], teams[1]].sort().join('|');
        if (seen[key]) continue;
        seen[key] = true;

        results.push([teams[0], teams[1]]);
    }
    return results;
}
"""
    try:
        raw = await page.evaluate(_JS)
        valid = set(TEAM_CODES)
        return [(t1, t2) for t1, t2 in raw if t1 in valid and t2 in valid]
    except Exception as exc:
        logger.error("DOM extraction gagal: %s", exc)
        return []



# ── Parser Standings ──────────────────────────────────────────────────────────

def parse_standings(text: str) -> dict:
    """
    Membaca teks halaman utama dan mengekstrak tabel standings.
    Format baris: TEAM MP MW-ML NGW GW-GL
    Contoh: ONIC 8 8 - 2 13 18 - 5
    """
    team_alt = "|".join(TEAM_CODES)
    # Match: TEAM  match_pts  match_w - match_l  net_game_win  game_w - game_l
    pattern = re.compile(
        rf"(?<!\w)({team_alt})\s+(\d+)\s+(\d+)\s*[-–]\s*(\d+)\s+(-?\d+)\s+(\d+)\s*[-–]\s*(\d+)"
    )

    standings: dict = {}
    for m in pattern.finditer(text):
        team = m.group(1)
        if team in standings:        # ambil entri pertama (deduplication)
            continue
        standings[team] = {
            "name":          team,
            "match_points":  int(m.group(2)),   # sama dengan wins
            "wins":          int(m.group(3)),
            "losses":        int(m.group(4)),
            "net_game_win":  int(m.group(5)),
            "game_wins":     int(m.group(6)),
            "game_losses":   int(m.group(7)),
            "logo":          TEAM_LOGOS.get(team, ""),
            "color":         TEAM_COLORS.get(team, "#888"),
        }

    # Fallback: isi tim yang tidak ditemukan dengan data hardcoded
    fallback = _fallback_standings()
    for team in fallback:
        if team not in standings:
            logger.warning("Tim %s tidak ditemukan di scrape, menggunakan fallback.", team)
            standings[team] = fallback[team]

    return standings

# ── Fallback Data (hardcoded berdasarkan data terkini S17) ───────────────────

def _fallback_standings() -> dict:
    """Data standings MPL ID S17 per Week 6 Day 2."""
    raw = [
        ("ONIC",  8, 8, 2,   13, 18,  5),
        ("DEWA",  7, 7, 3,    9, 16,  7),
        ("BTR",   6, 6, 4,    0, 13, 13),
        ("AE",    6, 6, 5,   -1, 15, 16),
        ("EVOS",  5, 5, 5,    1, 12, 11),
        ("TLID",  5, 5, 5,   -2, 11, 13),
        ("GEEK",  4, 4, 6,   -4, 10, 14),
        ("NAVI",  3, 3, 7,   -5, 10, 15),
        ("RRQ",   1, 1, 8,  -11,  5, 16),
    ]
    result = {}
    for team, mp, w, l, ngw, gw, gl in raw:
        result[team] = {
            "name":         team,
            "match_points": mp,
            "wins":         w,
            "losses":       l,
            "net_game_win": ngw,
            "game_wins":    gw,
            "game_losses":  gl,
            "logo":         TEAM_LOGOS.get(team, ""),
            "color":        TEAM_COLORS.get(team, "#888"),
        }
    return result


def _fallback_remaining_matches() -> list:
    """
    Jadwal sisa MPL ID S17 yang diketahui (per 3 Mei 2026).
    Digenerate dari debug DOM extraction pada halaman id-mpl.com/schedule.
    Dipakai sebagai safety-net jika DOM extraction ada match yang terlewat.
    """
    return [
        # ─ Week 6 - Day 3 (3 Mei) ─────────────────────
        ("NAVI",  "TLID"),
        ("ONIC",  "RRQ"),
        ("GEEK",  "EVOS"),
        # ─ Week 7 - Day 1 (8 Mei) ─────────────────────
        ("GEEK",  "DEWA"),
        ("BTR",   "TLID"),
        # ─ Week 7 - Day 2 (9 Mei) ─────────────────────
        ("DEWA",  "AE"),
        ("EVOS",  "RRQ"),
        ("ONIC",  "NAVI"),
        # ─ Week 7 - Day 3 (10 Mei) ────────────────────
        ("NAVI",  "BTR"),
        ("RRQ",   "GEEK"),
        ("TLID",  "EVOS"),
        # ─ Week 8 - Day 1 (15 Mei) ────────────────────
        ("DEWA",  "ONIC"),
        # ─ Week 8 - Day 2 (16 Mei) ────────────────────
        ("EVOS",  "NAVI"),
        ("ONIC",  "AE"),
        # ─ Week 8 - Day 3 (17 Mei) ────────────────────
        ("AE",    "BTR"),
        ("DEWA",  "EVOS"),
        ("RRQ",   "NAVI"),
        # ─ Week 9 - Day 1 (22 Mei) ────────────────────
        ("BTR",   "DEWA"),
        ("TLID",  "AE"),
        # ─ Week 9 - Day 2 (23 Mei) ────────────────────
        ("AE",    "RRQ"),
        ("BTR",   "ONIC"),
        # ─ Week 9 - Day 3 (24 Mei) ────────────────────
        ("NAVI",  "GEEK"),
        ("ONIC",  "EVOS"),
        ("RRQ",   "DEWA"),
    ]
