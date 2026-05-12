"""
Scraper untuk Liquipedia MPL ID S17 menggunakan Playwright (headless Chromium).
Mengambil standings dan jadwal pertandingan yang belum dimainkan.
"""

import re
import logging
from bs4 import BeautifulSoup
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
    "ONIC": "https://upload.wikimedia.org/wikipedia/en/f/f1/Logo_of_ONIC_Esports.png",
    "DEWA": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/dewa-64.png",
    "BTR":  "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/btr-64.png",
    "AE":   "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/ae-64.png",
    "EVOS": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/evos-64.png",
    "TLID": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/tlid-64.png",
    "GEEK": "https://wsrv.nl/?url=https://ik.imagekit.io/nloe8dhf7w/mplid/s14/teams/geek-64.png",
    "NAVI": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/NAVI-Logo.svg/960px-NAVI-Logo.svg.png",
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

        html: str = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        text: str = await page.evaluate("() => document.body.innerText")
        logger.info(
            "Liquipedia page fetched, html len: %d, text len: %d",
            len(html),
            len(text),
        )

        await browser.close()

    standings = parse_standings(soup)
    logger.info("Standings ditemukan: %s", list(standings.keys()))

    # remaining matches parser still uses innerText (text) for now
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

def parse_standings(soup_or_text) -> dict:
    """
    Parse standings. Accepts either a BeautifulSoup `soup` (preferred) or
    the raw `text` fallback (older implementation).
    """
    # If caller passed a BeautifulSoup object, use DOM parsing
    if not isinstance(soup_or_text, str):
        soup = soup_or_text
        standings: dict = {}

        # Find the main standings table: look for a wikitable with headers
        tables = soup.find_all("table", class_=lambda c: c and "wikitable" in c)
        standings_table = None
        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if any("match" in h for h in headers) and any("team" in h for h in headers):
                standings_table = table
                break

        if standings_table is None:
            logger.warning("Standings table not found via DOM, falling back to text parser")
            return parse_standings(str(soup.get_text()))

        trs = standings_table.find_all("tr")
        # collect toggle-area-content values (weeks/current) and pick the highest one
        toggles = []
        for tr in trs:
            if tr.has_attr("data-toggle-area-content"):
                try:
                    toggles.append(int(tr["data-toggle-area-content"]))
                except Exception:
                    pass

        if toggles:
            max_toggle = max(toggles)
            target_rows = [tr for tr in trs if tr.get("data-toggle-area-content") and int(tr["data-toggle-area-content"]) == max_toggle]
        else:
            target_rows = [tr for tr in trs if tr.find_all("td")]

        for tr in target_rows:
            tds = tr.find_all("td")
            if not tds:
                continue

            # Team name now in span.team-template-text > a (new HTML structure)
            team_cell = tds[0]
            team_span = team_cell.find("span", class_="team-template-text")
            
            if team_span:
                # New structure: span > a
                a = team_span.find("a")
                raw_name = a.get_text(strip=True) if a else team_span.get_text(strip=True)
            else:
                # Fallback to old structure: direct a in td
                a = team_cell.find("a")
                raw_name = a.get_text(strip=True) if a else team_cell.get_text(strip=True)

            # Map to team code using existing tolerant logic
            team_code = TEAM_NAME_MAP.get(raw_name)
            if not team_code:
                cleaned = re.sub(r"\s*\(.*?\)\s*", "", raw_name).strip()
                team_code = TEAM_NAME_MAP.get(cleaned)

            if not team_code:
                low = raw_name.lower()
                for k, v in TEAM_NAME_MAP.items():
                    if k.lower() == low or k.lower() in low or low in k.lower():
                        team_code = v
                        logger.debug("Matched team name '%s' -> '%s' via fuzzy rule", raw_name, k)
                        break

            if not team_code:
                logger.warning("Tim '%s' tidak dikenali saat parsing standings.", raw_name)
                continue

            # Parse columns: match (W-L), game (GW-GL), diff
            wins = losses = game_wins = game_losses = net_game_win = 0
            if len(tds) >= 2:
                match_text = tds[1].get_text(" ", strip=True)
                m = re.search(r"(\d+)\s*-\s*(\d+)", match_text)
                if m:
                    wins = int(m.group(1))
                    losses = int(m.group(2))

            if len(tds) >= 3:
                game_text = tds[2].get_text(" ", strip=True)
                m = re.search(r"(\d+)\s*-\s*(\d+)", game_text)
                if m:
                    game_wins = int(m.group(1))
                    game_losses = int(m.group(2))

            if len(tds) >= 4:
                diff_text = tds[3].get_text(strip=True).replace("+", "")
                try:
                    net_game_win = int(diff_text)
                except Exception:
                    net_game_win = 0

            standings[team_code] = {
                "name":         team_code,
                "match_points": wins,
                "wins":         wins,
                "losses":       losses,
                "net_game_win": net_game_win,
                "game_wins":    game_wins,
                "game_losses":  game_losses,
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

    # Otherwise assume a text string and run the original regex-based parser
    text: str = soup_or_text
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

    # Hapus marker perubahan peringkat seperti '▲1' / '▼3' (bisa muncul di baris sendiri
    # atau terpasang pada nama tim). Juga gabungkan baris di mana skor berada di baris
    # terpisah sehingga pola regex dapat menemukan semuanya pada satu baris.
    section = re.sub(r'^\s*[▲▼]\s*\d+\s*$', '', section, flags=re.MULTILINE)
    section = re.sub(r'[▲▼]\s*\d+', '', section)
    section = re.sub(r"\n\s*(\d+-\d+\s+\d+-\d+\s+[+-]?\d+)", r" \1", section)

    # Pattern: "N.  TEAM_NAME  W-L  GW-GL  +/-DIFF"
    pattern = re.compile(
        r"\d+\.\s+(.+?)\s+(\d+)-(\d+)\s+(\d+)-(\d+)\s+([+-]?\d+)",
        re.MULTILINE,
    )

    for m in pattern.finditer(section):
        raw_name = re.sub(r"\s+", " ", m.group(1)).strip()

        # Try direct lookup first, then several tolerant fallbacks:
        # 1) remove parenthetical suffixes (e.g. "Alter Ego (ID)")
        # 2) case-insensitive exact or substring match against keys in TEAM_NAME_MAP
        team_code = TEAM_NAME_MAP.get(raw_name)

        if not team_code:
            # remove any trailing parenthesis content
            cleaned = re.sub(r"\s*\(.*?\)\s*", "", raw_name).strip()
            team_code = TEAM_NAME_MAP.get(cleaned)

        if not team_code:
            # case-insensitive match or substring match
            low = raw_name.lower()
            for k, v in TEAM_NAME_MAP.items():
                if k.lower() == low or k.lower() in low or low in k.lower():
                    team_code = v
                    logger.debug("Matched team name '%s' -> '%s' via fuzzy rule", raw_name, k)
                    break

        if not team_code or team_code in standings:
            # skip unknown or duplicate entries; fallback later will fill missing teams
            if not team_code:
                logger.warning("Tim '%s' tidak dikenali saat parsing standings.", raw_name)
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
    """Data standings MPL ID S17 - Current (Updated per Liquipedia)."""
    raw = [
        ("ONIC",  10, 10, 2,  +17, 22,  5),
        ("DEWA",   8,  8, 4,   +9, 19, 10),
        ("TLID",   7,  7, 5,   +1, 15, 14),
        ("AE",     7,  7, 5,    0, 17, 17),
        ("EVOS",   6,  6, 6,   +1, 14, 13),
        ("BTR",    6,  6, 5,   -2, 13, 15),
        ("GEEK",   5,  5, 7,   -3, 13, 16),
        ("NAVI",   3,  3, 9,   -8, 11, 19),
        ("RRQ",    1,  1, 10, -15,  5, 20),
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
    Jadwal sisa MPL ID S17 (Updated per Liquipedia - Week 7 Day 2 sudah selesai).
    Week 7 Day 1-2 sudah dimainkan, sisa dari Day 3 Week 7 hingga Week 9.
    """
    return [
        # ─ Week 7 - Day 3 (Upcoming) ──────────────
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
