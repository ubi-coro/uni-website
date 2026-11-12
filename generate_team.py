# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "truststore", "pyyaml", "jinja2"]
# ///
"""Build the team page sections from team.yaml, filling contact details from PEVZ.

Run with: uv run generate_team.py [--out-dir DIR] [--ext html]

Writes one file per section and language (team_de_staff.html, …), because the section headings live in the CMS and each section has its own RXML block. People with a `pevz` id get email / phone / room from PEVZ unless team.yaml sets them. Anyone listed on the group's PEVZ org page but missing from team.yaml is reported as a warning.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from common import LANGS, comp_id, load_person, obfuscate, org_members

HERE = Path(__file__).parent
TEAM_DIR = "/fakultaeten/technische-fakultaet/arbeitsgruppen/kollaborative-robotik/team"
PLACEHOLDER_PHOTO = f"{TEAM_DIR}/unknown.jpg"

LABELS = {
    "de": {"phone": "Telefon", "room": "Raum", "profiles": "Profile"},
    "en": {"phone": "Telephone", "room": "Room", "profiles": "Profiles"},
}
ICONS = {
    "orcid": {"title": "ORCID", "file": "icon-orcid.svg"},
    "scholar": {"title": "Google Scholar", "file": "icon-google-scholar.svg"},
    "linkedin": {"title": "LinkedIn", "file": "icon-linkedin.svg"},
}
TEXT_LINKS = {"openreview": "OpenReview", "researchgate": "ResearchGate"}
CONTACT_FIELDS = ("email", "phone", "room")


def merge(entry: dict, pevz) -> dict:
    """team.yaml wins over PEVZ, field by field."""
    from_pevz = {"email": pevz.email, "phone": pevz.phone, "room": pevz.office} if pevz else {}
    person = {k: entry.get(k) or from_pevz.get(k, "") for k in CONTACT_FIELDS}
    unknown = set(entry.get("links") or {}) - set(ICONS) - set(TEXT_LINKS)
    if unknown:
        sys.exit(f"{entry['name']}: unknown link type(s) {', '.join(sorted(unknown))}")
    return person | {
        "name": entry["name"],
        "photo": entry.get("photo") or PLACEHOLDER_PHOTO,
        "links": entry.get("links") or {},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--ext", default="html", help="file extension of the output files")
    args = parser.parse_args()

    sections = yaml.safe_load((HERE / "team.yaml").read_text(encoding="utf-8"))
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
    template = env.get_template("team_section.html")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for section, entries in sections.items():
        people = [merge(e, pevz.get(e.get("pevz"))) for e in entries]
        print(f"{section}: {', '.join(p['name'] for p in people)}")
        for lang in LANGS:
            for p in people:
                p["anchor"] = comp_id("team", lang, section, p["name"])
            html = template.render(people=people, L=LABELS[lang], icons=ICONS, text_links=TEXT_LINKS, icon_base=TEAM_DIR)
            out = args.out_dir / f"team_{lang}_{section}.{args.ext}"
            out.write_text(html.lstrip("\n"), encoding="utf-8")
    print(f"wrote {len(sections) * len(LANGS)} files to {args.out_dir}")


if __name__ == "__main__":
    main()
