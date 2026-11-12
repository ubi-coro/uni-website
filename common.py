"""Shared helpers for the page generators: fetching and parsing eKVV / PEVZ, plus small rendering utilities."""

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import truststore
import yaml
from bs4 import BeautifulSoup

# Use the OS trust store, like curl and browsers do
truststore.inject_into_ssl()

EKVV = "https://ekvv.uni-bielefeld.de"
LANGS = ("de", "en")

# Technische Fakultät / Arbeitsgruppen / Kollaborative Robotik
ORG_ID = 429911235


# --- Fetching -------------------------------------------------------------

# Caps concurrent requests across all worker threads, to stay under eKVV's rate limit
_in_flight = threading.Semaphore(3)
RETRIES = 4

def fetch(path: str) -> BeautifulSoup:
    req = Request(EKVV + path, headers={"User-Agent": "page-generator (AG Kollaborative Robotik)"})
    for attempt in range(RETRIES + 1):
        try:
            with _in_flight, urlopen(req, timeout=30) as resp:
                return BeautifulSoup(resp.read().decode("utf-8"), "html.parser")
        except HTTPError as e:
            # eKVV rate-limits (429), noticeably harder from GitHub's runners than from a desktop
            if attempt == RETRIES or (e.code != 429 and e.code < 500):
                raise
            retry_after = e.headers.get("Retry-After", "")
            time.sleep(int(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1))


def text(node) -> str:
    return " ".join(node.get_text(" ").split()) if node else ""


def inner_html(node) -> str:
    return "".join(str(c) for c in node.contents).strip() if node else ""


# --- PEVZ -----------------------------------------------------------------

@dataclass
class Person:
    """Contact details from PEVZ. E-mail addresses are deliberately not scraped (PEVZ protects them against harvesting); they come from team.yaml."""
    id: int
    name: str
    photo: str
    phone: str
    phone_sekr: str
    office: str
    role: str


def org_members(org_id: int = ORG_ID) -> list[int]:
    soup = fetch(f"/pers_publ/publ/EinrichtungDetail.jsp?orgId={org_id}")
    return sorted({int(m) for a in soup.select('a[href*="PersonDetail"]') for m in re.findall(r"[?&]personId=(\d+)", a["href"])})


def contact_block(soup: BeautifulSoup):
    """The contact entry for our group, else the first one with contact details."""
    blocks = soup.select("div.person_kontakt")
    for block in blocks:
        if "Arbeitsgruppen / Kollaborative Robotik" in text(block.select_one("h3")):
            return block
    return next((b for b in blocks if b.select_one("dl.kontakt dt")), blocks[0] if blocks else None)


def load_person(person_id: int) -> Person:
    soup = fetch(f"/pers_publ/publ/PersonDetail.jsp?personId={person_id}")
    block = contact_block(soup)
    details = {}
    if block:
        for dt in block.select("dl.kontakt dt"):
            dd = dt.find_next_sibling("dd")
            # Drop the room-plan / secretary links that trail the actual value
            for extra in dd.select(".not_in_print_version, a[href*='sekretariat']"):
                extra.decompose()
            details[text(dt)] = text(dd).rstrip(" −")
    photo = soup.select_one("img.foto")
    return Person(
        id=person_id,
        name=re.sub(r"^(Herr|Frau)\s+", "", text(soup.select_one("h1"))),
        photo=photo.parent["href"] if photo and photo.parent.name == "a" else (photo["src"] if photo else ""),
        phone=details.get("Telefon", ""),
        phone_sekr=details.get("Telefon Sekretariat", ""),
        office=details.get("Büro", ""),
        role=inner_html(block.select_one("dl.aufgabenbeschreibung dd")) if block else "",
    )


# --- team.yaml ------------------------------------------------------------

def load_team() -> dict[str, list[dict]]:
    return yaml.safe_load((Path(__file__).parent / "team.yaml").read_text(encoding="utf-8")) or {}


def team_emails() -> dict[int, str]:
    """PEVZ id -> e-mail address, for everyone in team.yaml who has both."""
    return {e["pevz"]: e["email"] for people in load_team().values() for e in people if e.get("pevz") and e.get("email")}


# --- Rendering ------------------------------------------------------------

def comp_id(*key) -> str:
    """Deterministic id in the CMS's comp_XXXXXXXXXXXX_XXXXXXXXXX_XXXX format."""
    h = hashlib.sha1("|".join(map(str, key)).encode()).hexdigest()
    return f"comp_{h[:12]}_{h[12:22]}_{h[22:26]}"


def obfuscate(s: str) -> str:
    return "".join(f"&#{ord(c)};" for c in s)


def indent(block: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else "" for line in block.splitlines())
