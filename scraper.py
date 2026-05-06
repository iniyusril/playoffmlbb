"""
Scraper untuk Liquipedia MPL ID S17 menggunakan Playwright (headless Chromium).
Mengambil standings dan jadwal pertandingan yang belum dimainkan.
"""

import re
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

LIQUIPEDIA_URL = (
    "https://liquipedia.net/mobilelegends/MPL/Indonesia/Season_17/Regular_Season"
)

TEAM_CODES = ["ONIC", "DEWA", "BTR", "AE", "EVOS", "TLID", "GEEK", "NAVI", "RRQ"]

# Nama lengkap di Liquipedia → kode pendek yang dipakai simulator
TEAM_NAME_MAP = {
    "ONIC":                    "ONIC",
    "EVOS":                    "EVOS",
    "Dewa United Esports":     "DEWA",
    "Bigetron by Vitality":    "BTR",
    "Team Liquid ID":          "TLID",
    "Alter Ego":               "AE",
    "Geek Fam ID":             "GEEK",
    "Natus Vincere":           "NAVI",
    "RRQ Hoshi":               "RRQ",
}

TEAM_LOGOS = {
    "ONIC": "https://cdn.id-mpl.com/data/teams/onic-b-64.png?X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=DO00UK9XG63MGT2KWV9H%2F20260506%2Fsgp1%2Fs3%2Faws4_request&X-Amz-Date=20260506T010653Z&X-Amz-SignedHeaders=host&X-Amz-Expires=21600&X-Amz-Signature=6970805dc67cc9287195c172f431d6349bb4e3b8a380b2506ee6c0fa59ae0f45",
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
    Scrape standings dan remaining matches dari Liquipedia MPL ID S17.
    Returns dict: { standings: dict, remaining_matches: list[tuple] }
    """
    logger.info("Memulai scraping Liquipedia MPL ID S17 ...")

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
        page.set_default_timeout(45_000)

        await page.goto(LIQUIPEDIA_URL, wait_until="networkidle")
        # Tunggu konten dinamis ter-render
        await page.wait_for_timeout(4_000)

        text: str = await page.evaluate("() => document.body.innerText")
        logger.info("Liquipedia page fetched, panjang text: %d", len(text))

        await browser.close()

    standings = parse_standings(text)
    logger.info("Standings ditemukan: %s", list(standings.keys()))

    remaining = parse_remaining_matches(text)
    logger.info("Remaining matches: %d pertandingan", len(remaining))

    # Fallback: isi tim/match yang gagal di-parse
    fallback_st = _fallback_standings()
    for team in fallback_st:
        if team not in standings:
            logger.warning("Tim %s tidak ditemukan, menggunakan fallback.", team)
            standings[team] = fallback_st[team]

    if len(remaining) < 5:
        logger.warning(
            "Remaining matches terlalu sedikit (%d), menggunakan fallback.", len(remaining)
        )
        remaining = _fallback_remaining_matches()

    return {"standings": standings, "remaining_matches": remaining}



# ── Parser Standings ──────────────────────────────────────────────────────────

def parse_standings(text: str) -> dict:
    """
    Parse standings dari Liquipedia innerText.
    Format baris: N.  TEAM_NAME  W-L  GW-GL  +/-DIFF
    TEAM_NAME bisa berisi spasi (misal: "Dewa United Esports").
    """
    standings: dict = {}

    # Cari batas section standings (antara "Regular Season[edit]" dan H2H/tiebreaker)
    start = text.find("Regular Season[edit]")
    if start != -1:
        start += len("Regular Season[edit]")
    else:
        start = text.find("# Team")
        if start == -1:
            start = 0

    end = len(text)
    for marker in ("Tiebreakers:", "Show Individual", "Detailed Results"):
        pos = text.find(marker, start)
        if pos != -1 and pos < end:
            end = pos

    section = text[start:end]

    # Pattern: "N.  TEAM_NAME  W-L  GW-GL  +/-DIFF"
    pattern = re.compile(
        r"\d+\.\s+(.+?)\s+(\d+)-(\d+)\s+(\d+)-(\d+)\s+([+-]?\d+)",
        re.MULTILINE,
    )

    for m in pattern.finditer(section):
        raw_name = re.sub(r"\s+", " ", m.group(1)).strip()
        team_code = TEAM_NAME_MAP.get(raw_name)
        if not team_code or team_code in standings:
            continue

        standings[team_code] = {
            "name":         team_code,
            "match_points": int(m.group(2)),
            "wins":         int(m.group(2)),
            "losses":       int(m.group(3)),
            "net_game_win": int(m.group(6)),
            "game_wins":    int(m.group(4)),
            "game_losses":  int(m.group(5)),
            "logo":         TEAM_LOGOS.get(team_code, ""),
            "color":        TEAM_COLORS.get(team_code, "#888"),
        }

    # Fallback: isi tim yang tidak ditemukan dengan data hardcoded
    fallback = _fallback_standings()
    for team in fallback:
        if team not in standings:
            logger.warning("Tim %s tidak ditemukan di scrape, menggunakan fallback.", team)
            standings[team] = fallback[team]

    return standings


# ── Parser Jadwal Tersisa ─────────────────────────────────────────────────────

def parse_remaining_matches(text: str) -> list:
    """
    Parse sisa pertandingan dari weekly schedule Liquipedia.

    Format completed : TEAM1 \\n SCORE1 \\n SCORE2 \\n TEAM2   (score > 0)
    Format upcoming  : TEAM1 \\n TEAM2                         (tanpa skor)
    Format 0-0 / live: TEAM1 \\n 0 \\n 0 \\n TEAM2             (dianggap tersisa)

    Di Liquipedia, setiap pertandingan hanya muncul sekali sehingga
    deduplication tidak dibutuhkan.
    """
    VALID = set(TEAM_CODES)

    # Mulai dari weekly schedule (setelah H2H / "Show Individual")
    anchor = text.find("Show Individual")
    if anchor == -1:
        anchor = text.find("Tiebreakers:")
    search_from = anchor if anchor != -1 else 0

    # Cari "Week 1" pertama dalam section schedule (bukan di TOC)
    week1_pos = text.find("Week 1", search_from)
    if week1_pos == -1:
        return []

    # Cari akhir section sebelum footer
    end = len(text)
    for marker in ("Send an email", "Privacy policy", "About Liquipedia"):
        pos = text.find(marker, week1_pos)
        if pos != -1 and pos < end:
            end = pos

    section = text[week1_pos:end]
    lines = [l.strip() for l in section.split("\n") if l.strip()]

    remaining = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line not in VALID:
            i += 1
            continue

        team1 = line
        if i + 1 >= len(lines):
            break

        next1 = lines[i + 1]

        if next1 in VALID:
            # Format upcoming: langsung diikuti tim kedua (tanpa skor)
            remaining.append((team1, next1))
            i += 2

        elif next1 in ("0", "1", "2") and i + 3 < len(lines):
            # Kemungkinan ada skor
            score2_str = lines[i + 2]
            team2_cand  = lines[i + 3]
            if score2_str in ("0", "1", "2") and team2_cand in VALID:
                if int(next1) == 0 and int(score2_str) == 0:
                    # 0-0 = belum dimainkan / sedang berlangsung
                    remaining.append((team1, team2_cand))
                # else: sudah selesai, lewati
                i += 4
            else:
                i += 1
        else:
            i += 1

    return remaining


# ── Fallback Data (hardcoded berdasarkan data terkini S17) ───────────────────

def _fallback_standings() -> dict:
    """Data standings MPL ID S17 per Week 6 Day 3 (setelah NAVI vs TLID selesai)."""
    raw = [
        ("ONIC",  8, 8, 2,   13, 18,  5),
        ("DEWA",  7, 7, 3,    9, 16,  7),
        ("BTR",   6, 6, 4,    0, 13, 13),
        ("TLID",  6, 6, 5,   -1, 13, 14),
        ("AE",    6, 6, 5,   -1, 15, 16),
        ("EVOS",  5, 5, 5,    1, 12, 11),
        ("GEEK",  4, 4, 6,   -4, 10, 14),
        ("NAVI",  3, 3, 8,   -6, 11, 17),
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
    Jadwal sisa MPL ID S17 (per Week 6 Day 3, berdasarkan Liquipedia).
    NAVI vs TLID sudah selesai (1-2), tidak termasuk di sini.
    """
    return [
        # ─ Week 6 - Day 3 ────────────────────────────
        ("ONIC",  "RRQ"),
        ("GEEK",  "EVOS"),
        # ─ Week 7 - Day 1 ────────────────────────────
        ("GEEK",  "DEWA"),
        ("BTR",   "TLID"),
        # ─ Week 7 - Day 2 ────────────────────────────
        ("DEWA",  "AE"),
        ("EVOS",  "RRQ"),
        ("ONIC",  "NAVI"),
        # ─ Week 7 - Day 3 ────────────────────────────
        ("RRQ",   "GEEK"),
        ("NAVI",  "BTR"),
        ("TLID",  "EVOS"),
        # ─ Week 8 - Day 1 ────────────────────────────
        ("BTR",   "GEEK"),
        ("DEWA",  "ONIC"),
        # ─ Week 8 - Day 2 ────────────────────────────
        ("EVOS",  "NAVI"),
        ("TLID",  "RRQ"),
        ("ONIC",  "AE"),
        # ─ Week 8 - Day 3 ────────────────────────────
        ("DEWA",  "EVOS"),
        ("AE",    "BTR"),
        ("RRQ",   "NAVI"),
        # ─ Week 9 - Day 1 ────────────────────────────
        ("BTR",   "DEWA"),
        ("TLID",  "AE"),
        # ─ Week 9 - Day 2 ────────────────────────────
        ("GEEK",  "TLID"),
        ("AE",    "RRQ"),
        ("BTR",   "ONIC"),
        # ─ Week 9 - Day 3 ────────────────────────────
        ("RRQ",   "DEWA"),
        ("ONIC",  "EVOS"),
        ("NAVI",  "GEEK"),
    ]
