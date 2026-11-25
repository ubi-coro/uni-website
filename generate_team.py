# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "truststore", "pyyaml", "jinja2"]
# ///
"""Build the team page sections from team.yaml, filling contact details from PEVZ.

Run with: uv run generate_team.py [--out-dir DIR] [--ext html]

Writes, per language:
- team_<lang>_grid.html: everyone as a photo grid, ordered by section, then by surname; hovering or tapping a photo shows contact details and a link to the profile page
- team_<lang>_profiles.html: every profile on one page, CSS :target shows the one named in the URL hash (PROFILE_PAGE#slug)
- team_<lang>_<section>.html: the older per-section contact cards, kept so the CMS can switch back

People with a `pevz` id get phone / room from PEVZ unless team.yaml sets them; e-mail addresses always come from team.yaml. Anyone listed on the group's PEVZ org page but missing from team.yaml is reported as a warning.
"""

import argparse
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from common import LANGS, comp_id, load_person, load_team, obfuscate, org_members

HERE = Path(__file__).parent
TEAM_DIR = "/fakultaeten/technische-fakultaet/arbeitsgruppen/kollaborative-robotik/team"
PLACEHOLDER_PHOTO = f"{TEAM_DIR}/unknown.jpg"
# The CMS page whose RXML block inserts team_<lang>_profiles.html; the grid links to PROFILE_PAGE#<slug>
PROFILE_PAGE = f"{TEAM_DIR}/profil/"

# Each person's position, by team.yaml section; the sections' order is the grid's order. A person's own `position` overrides it.
POSITIONS = {
    "head": {"de": "Leitung", "en": "Head of Group"},
    "postdocs": {"de": "Postdoktorand:in", "en": "Senior Researcher"},
    "admin": {"de": "Teamassistenz", "en": "Team Assistant"},
    "staff": {"de": "Wissenschaftliche:r Mitarbeiter:in", "en": "Research Associate"},
    "joint": {"de": "Kooperative Promotion", "en": "Joint Doctorate"},
}

LABELS = {
    "de": {
        "phone": "Telefon",
        "room": "Raum",
        "email": "E-Mail",
        "profiles": "Profile",
        "more": "Mehr erfahren",
        "back": "Zurück zum Team",
        "supervisor": "Betreuung an der Partnerinstitution",
        "no_profile": "Wähle eine Person auf der Teamseite aus, um ihr Profil zu sehen.",
    },
    "en": {
        "phone": "Telephone",
        "room": "Room",
        "email": "E-mail",
        "profiles": "Profiles",
        "more": "More info",
        "back": "Back to the team",
        "supervisor": "Supervisor at the partner institution",
        "no_profile": "Pick someone on the team page to see their profile.",
    },
}
ICONS = {
    "orcid": {"title": "ORCID", "file": "icon-orcid.svg"},
    "scholar": {"title": "Google Scholar", "file": "icon-google-scholar.svg"},
    "linkedin": {"title": "LinkedIn", "file": "icon-linkedin.svg"},
    "researchgate": {"title": "ResearchGate", "file": "icon-researchgate.svg"},
}
TEXT_LINKS = {"openreview": "OpenReview"}
CONTACT_FIELDS = ("email", "phone", "room")


def fold(s: str) -> str:
    """Lowercase ASCII: accents and umlauts lose their marks (ö -> o, as DIN 5007 sorts them)."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().casefold()


def plain_name(name: str) -> str:
    """The name without academic titles, i.e. without the tokens that contain a dot (Prof., Dr., rer. nat., Dr.-Ing.)."""
    return " ".join(t for t in name.split() if "." not in t)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(plain_name(name))).strip("-")


def sort_key(entry: dict) -> str:
    """Surname first, then the full name. The surname defaults to the last word; `sortname` sets it for names like "Meyer zu Theenhausen"."""
    return fold(f"{entry.get('sortname') or plain_name(entry['name']).split()[-1]} {plain_name(entry['name'])}")


def merge(entry: dict, pevz) -> dict:
    """team.yaml wins over PEVZ, field by field. E-mail addresses only ever come from team.yaml."""
    from_pevz = {"phone": pevz.phone, "room": pevz.office} if pevz else {}
    person = {k: entry.get(k) or from_pevz.get(k, "") for k in CONTACT_FIELDS}
    unknown = set(entry.get("links") or {}) - set(ICONS) - set(TEXT_LINKS)
    if unknown:
        sys.exit(f"{entry['name']}: unknown link type(s) {', '.join(sorted(unknown))}")
    return person | {
        "name": entry["name"],
        "photo": entry.get("photo") or PLACEHOLDER_PHOTO,
        "links": entry.get("links") or {},
        "supervisor": entry.get("supervisor"),
        "intro": entry.get("intro"),
        "position": entry.get("position"),
        "slug": slug(entry["name"]),
    }


def paragraphs(text: str) -> Markup:
    """Blank lines separate paragraphs, single line breaks become <br/>; the text itself stays escaped."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return Markup("\n").join(Markup("<p>%s</p>") % Markup("<br/>\n").join(escape(line.strip()) for line in b.splitlines()) for b in blocks)


def localize(value, lang: str) -> str:
    """value is either one string for both pages or {de: …, en: …}; a missing language falls back to the other."""
    if not value or isinstance(value, str):
        return value or ""
    return value.get(lang) or next((v for v in value.values() if v), "")


def email_html(address: str) -> Markup:
    """The address as obfuscated text, with a line-break opportunity before the @ so it wraps cleanly in a narrow tile."""
    local, _, domain = address.partition("@")
    return Markup(obfuscate(local) + "<wbr/>" + obfuscate("@" + domain))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--ext", default="html", help="file extension of the output files")
    args = parser.parse_args()

    sections = load_team()
    if not sections or not any(sections.values()):
        sys.exit("team.yaml lists nobody")

    ids = sorted({e["pevz"] for people in sections.values() for e in people if e.get("pevz")})
    with ThreadPoolExecutor(max_workers=6) as pool:
        members = org_members()
        pevz = dict(zip(ids, pool.map(load_person, ids)))

    for pid in sorted(set(members) - set(ids)):
        # GitHub turns this into an annotation on the workflow run
        print(f"::warning::PEVZ org member {pid} is not in team.yaml (https://ekvv.uni-bielefeld.de/pers_publ/publ/PersonDetail.jsp?personId={pid})")

    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=True, keep_trailing_newline=True)
    env.filters["obfuscate"] = lambda s: Markup(obfuscate(s))
    env.filters["paragraphs"] = paragraphs
    env.filters["email_html"] = email_html
    section_template = env.get_template("team_section.html")
    grid_template = env.get_template("team_grid.html")
    profiles_template = env.get_template("team_profiles.html")

    unknown = set(sections) - set(POSITIONS)
    if unknown:
        sys.exit(f"team.yaml: no position for section(s) {', '.join(sorted(unknown))}; add them to POSITIONS")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    def write(name: str, html: str):
        nonlocal written
        (args.out_dir / f"{name}.{args.ext}").write_text(html.lstrip("\n"), encoding="utf-8")
        written += 1

    everyone = []  # (section, person) in grid order
    for section, entries in sections.items():
        merged = [(e, merge(e, pevz.get(e.get("pevz")))) for e in entries]
        people = [p for _, p in merged]
        print(f"{section}: {', '.join(p['name'] for p in people)}")
        everyone += [(section, p) for e, p in sorted(merged, key=lambda ep: sort_key(ep[0]))]
        for lang in LANGS:
            people_lang = [p | {"anchor": comp_id("team", lang, section, p["name"]), "intro": localize(p["intro"], lang)} for p in people]
            write(f"team_{lang}_{section}", section_template.render(people=people_lang, L=LABELS[lang], icons=ICONS, text_links=TEXT_LINKS, icon_base=TEAM_DIR))

    slugs = [p["slug"] for _, p in everyone]
    if dupes := sorted({s for s in slugs if slugs.count(s) > 1}):
        sys.exit(f"team.yaml: several people share the profile slug {', '.join(dupes)}")

    for lang in LANGS:
        people = [p | {"intro": localize(p["intro"], lang), "position": localize(p["position"] or POSITIONS[section], lang)} for section, p in everyone]
        context = {"people": people, "L": LABELS[lang], "icons": ICONS, "text_links": TEXT_LINKS, "icon_base": TEAM_DIR, "profile_page": PROFILE_PAGE, "team_page": f"{TEAM_DIR}/"}
        write(f"team_{lang}_grid", grid_template.render(context))
        write(f"team_{lang}_profiles", profiles_template.render(context))
    print(f"wrote {written} files to {args.out_dir}")


if __name__ == "__main__":
    main()
