# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "truststore", "pyyaml"]
# ///
"""Build teaching_de.xml and teaching_en.xml from eKVV / PEVZ.

Run with: uv run generate_teaching.py [--out-dir DIR] [--ext html]

Team members come from the PEVZ org page of the group, plus EXTRA_PERSON_IDS. Every course they teach (eKVV, all semesters) is collected, filtered, and rendered as one CMS accordion per semester, newest first. Course text is entered once in eKVV, so it is fetched once and only the labels differ between the two files.
"""

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from common import EKVV, Person, comp_id, fetch, indent, inner_html, load_person, obfuscate, org_members, team_emails, text

# People who teach with us but aren't listed on the org page
EXTRA_PERSON_IDS: list[int] = []

FIRST_SEMESTER = "SoSe 2024"
COURSE_TYPES = {"S", "V", "Ü"}
EXCLUDE_TITLE_PREFIXES = ("AG Seminar",)
# eKVV course ids (vd?id=…) to leave out by hand
EXCLUDE_COURSE_IDS: set[int] = set()

TEAM_EMAILS = team_emails()

LABELS = {
    "de": {
        "prereq": "Teilnahmevoraussetzungen, notwendige Vorkenntnisse",
        "staff": "Lehrende",
        "link": "↗ eKVV Eintrag",
        "phone": "Telefon",
        "phone_sekr": "Telefon Sekr.",
        "office": "Büro",
        "pevz": "Im PEVZ anzeigen",
    },
    "en": {
        "prereq": "Requirements for participation, required level",
        "staff": "Teaching staff",
        "link": "↗ Further information on eKVV",
        "phone": "Phone",
        "phone_sekr": "Telephone secretary",
        "office": "Office",
        "pevz": "Show in PEVZ",
    },
}


# --- Semesters ------------------------------------------------------------


def semester_key(name: str) -> int:
    """'SoSe 2025' -> 4050, 'WiSe 2025/2026' -> 4051."""
    year = int(re.search(r"\d{4}", name).group())
    return year * 2 + name.startswith("WiSe")


def semester_label(name: str, lang: str) -> str:
    years = re.findall(r"\d{4}", name)
    if name.startswith("WiSe"):
        return f"WiSe {years[0][2:]}/{years[1][2:]}" if lang == "de" else f"Winter term {years[0]}/{years[1]}"
    return f"SoSe {years[0][2:]}" if lang == "de" else f"Summer term {years[0]}"


# --- Data -----------------------------------------------------------------


@dataclass
class Course:
    id: int
    number: str
    title: str
    type: str
    semester: str
    description: str = ""
    prerequisites: str = ""
    lecturers: list[int] = field(default_factory=list)


def team_members() -> list[int]:
    return sorted(set(org_members()) | set(EXTRA_PERSON_IDS))


def courses_of(person_id: int) -> list[Course]:
    soup = fetch(f"/kvv_publ/publ/Lehrende_Veranstaltungen.jsp?personId={person_id}&zeigeAlle=1")
    courses = []
    for h2 in soup.select("h2.linie_top_grau"):
        semester = text(h2)
        table = h2.find_next_sibling("table")
        if not table:
            continue
        for row in table.select("tbody tr"):
            link = row.select_one("td.thema a[href*='vd']")
            if not link:
                continue
            courses.append(
                Course(
                    id=int(re.search(r"[?&]id=(\d+)", link["href"]).group(1)),
                    number=text(row.select_one("td.belegnr")),
                    title=text(link),
                    type=text(row.select_one("td.art")),
                    semester=semester,
                )
            )
    return courses


def keep(course: Course, same_semester: list[Course]) -> bool:
    if course.id in EXCLUDE_COURSE_IDS or semester_key(course.semester) < semester_key(FIRST_SEMESTER):
        return False
    if course.type not in COURSE_TYPES or course.title.startswith(EXCLUDE_TITLE_PREFIXES):
        return False
    if course.type == "Ü":
        # Only exercises for our own lectures/seminars ("Übungen: X" next to "X"), not tutorials we run for other groups. An exercise with the exact same title as its seminar adds nothing.
        base = re.sub(r"^(Übungen?|Tutorials?)[^:]*:\s*", "", course.title)
        return base != course.title and any(c.title == base and c.type != "Ü" for c in same_semester)
    return True


def load_details(course: Course) -> Course:
    soup = fetch(f"/kvv_publ/publ/vd?id={course.id}")
    course.description = "\n".join(inner_html(dd) for dd in soup.select("#kommentar dd:not([id])"))
    course.prerequisites = inner_html(soup.select_one("dd#voraussetzungen"))
    course.lecturers = [int(re.search(r"[?&]id=(\d+)", a["href"]).group(1)) for a in soup.select("#lehrendenliste a[href*='lehrende_DetailAct']")]
    return course


# --- Rendering ------------------------------------------------------------


def text_block(html: str, anchor: str) -> str:
    return f"""<div class="ubf-contentBlock ubf-contentBlock--text">
    <a class="ubf-anchor" id="{anchor}"></a>
    <div class="ubf-contentBlock__text ubf-text">
        <div class="ubf-text__content ubf-ugc" data-ubf-component="UserGeneratedContent">
{indent(html, 12)}
        </div>
    </div>
</div>"""


def contact_card(p: Person, lang: str, anchor: str) -> str:
    L = LABELS[lang]
    name = escape(p.name)
    img = (
        f"""
            <div class="ubf-contact__img">
                <figure class="ubf-contact__figure" data-type="image">
                    <img alt="{name} (Photo)" class="ubf-picture__img ubf-js-loaded" draggable="false" src="{escape(p.photo)}"/>
                </figure>
            </div>"""
        if p.photo
        else ""
    )
    # Only group members have an address (from team.yaml); PEVZ addresses aren't scraped, and external lecturers keep the PEVZ button
    email = TEAM_EMAILS.get(p.id, "")
    mail = (
        f"""
            <p class="ubf-contact__mail">
                <a class="ubf-contact__link" href="{obfuscate("mailto:" + email)}">{obfuscate(email)}</a>
            </p>"""
        if email
        else ""
    )
    rows = []
    if p.phone:
        rows.append((L["phone"], f'<a href="tel:{escape(p.phone)}" target="_blank">{escape(p.phone)}</a>'))
    if p.phone_sekr:
        rows.append((L["phone_sekr"], f'<a href="tel:{escape(p.phone_sekr)}" target="_blank">{escape(p.phone_sekr)}</a>'))
    if p.office:
        rows.append((L["office"], escape(p.office)))
    details = "".join(
        f"""
                <dt class="ubf-contact__detailName">{k}</dt>
                <dd class="ubf-contact__detailValue">{v}</dd>"""
        for k, v in rows
    )
    return f"""<div class="ubf-contentBlock ubf-contentBlock--contact ">
    <a class="ubf-anchor" id="{anchor}"></a>
    <div class="ubf-contact">
        <div class="ubf-contact__content ubf-ugc">
            <div class="ubf-contact__info">
                <h3 class="ubf-contact__title">{name}</h3>{img}
                <div class="ubf-contact__role">
                    <role>{p.role}</role>
                </div>{mail}
                <dl class="ubf-contact__details ubf-ugc__dl--compact">{details}
                </dl>
            </div>
            <div class="ubf-contact__pevzButton">
                <a class="ubf-button ubf-contact__button" href="{EKVV}/pers_publ/publ/PersonDetail.jsp?personId={p.id}" target="_blank">{L["pevz"]}</a>
            </div>
        </div>
    </div>
</div>"""


def course_item(c: Course, people: dict[int, Person], lang: str) -> str:
    L = LABELS[lang]
    acc = "accordion-" + comp_id(lang, c.id)
    blocks = []
    if c.description:
        blocks.append(text_block(c.description, comp_id(lang, c.id, "desc")))
    if c.prerequisites:
        blocks.append(text_block(f"<h4>{L['prereq']}</h4>\n{c.prerequisites}", comp_id(lang, c.id, "prereq")))
    blocks.append(text_block(f"<h4>{L['staff']}</h4>", comp_id(lang, c.id, "staff")))
    blocks += [contact_card(people[pid], lang, comp_id(lang, c.id, "person", pid)) for pid in c.lecturers]
    link = f'<p>\n    <a data-ubf-link="" data-ubf-trigger-collapsable="" href="{EKVV}/kvv_publ/publ/vd?id={c.id}" target="_self">{L["link"]}</a>\n</p>'
    blocks.append(text_block(link, comp_id(lang, c.id, "link")))
    label = escape(f"{c.number} {c.title} ({c.type})")
    # Inside an RXML block `.ubf-ugc dt {display: block}` outranks the accordion's flex, which strands the icon next to the label. The icon is an inline path because the page's #triangle-right sprite isn't reliably there.
    return f"""<dt class="ubf-accordion__toggler" style="display: flex;">
    <a class="ubf-anchor" id="{acc}"></a>
    <a aria-expanded="false" class="ubf-accordion__togglerLink " data-ubf-component="Toggler" data-ubf-target-data-attribute-id="true" href="#{acc}" role="button" target="_SELF">
        <span class="ubf-accordion__togglerLabel">{label}</span>
    </a>
    <span aria-hidden="true" class="ubf-accordion__togglerIcon">
        <span data-type="svg">
            <canvas height="22" width="17">
            </canvas>
            <svg aria-labelledby="icon-{acc[10:]}" focusable="false" role="img" viewBox="0 0 17 22">
                <title id="icon-{acc[10:]}"></title>
                <path d="M16 10.92L1 21V1l15 9.92z"/>
            </svg>
        </span>
    </span>
</dt>

<dd class="ubf-accordion__contentWrapper">
    <div class="ubf-accordion__content ubf-js-collapsed" data-ubf-component="Collapsable" data-ubf-id="{acc}" id="" tabindex="-1">
{indent(chr(10).join(blocks), 8)}
    </div>
</dd>"""


def render(semesters: dict[str, list[Course]], people: dict[int, Person], lang: str) -> str:
    sections = []
    for sem, courses in semesters.items():
        items = "\n\n".join(course_item(c, people, lang) for c in courses)
        sections.append(f"""<div class="ubf-contentBlock ubf-contentBlock--accordion">
    <a class="ubf-anchor" id="{comp_id(lang, sem)}"></a>
    <h3 class="ubf-contentBlock__title">{semester_label(sem, lang)}</h3>

    <dl class="ubf-contentBlock__accordion ubf-accordion ubf-accordion--boxed" data-ubf-component="Accordion">

{indent(items, 8)}

    </dl>
</div>""")
    return f'<div class="ubf-section__content">\n\n{indent(chr(10).join(sections), 4)}\n</div>\n'


# --- Main -----------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--ext", default="xml", help="file extension of the output files")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=6) as pool:
        members = team_members()
        print(f"{len(members)} team members")

        found = {c.id: c for cs in pool.map(courses_of, members) for c in cs}
        by_semester: dict[str, list[Course]] = {}
        for c in found.values():
            by_semester.setdefault(c.semester, []).append(c)
        courses = [c for cs in by_semester.values() for c in cs if keep(c, cs)]
        # An empty page would silently replace the live one, so treat it as a scraper failure
        if not courses:
            sys.exit("No courses found; has the eKVV markup changed?")
        courses = list(pool.map(load_details, courses))

        lecturer_ids = sorted({pid for c in courses for pid in c.lecturers})
        people = {p.id: p for p in pool.map(load_person, lecturer_ids)}

    semesters: dict[str, list[Course]] = {}
    for c in sorted(courses, key=lambda c: (-semester_key(c.semester), c.number, c.title)):
        semesters.setdefault(c.semester, []).append(c)

    for sem, cs in semesters.items():
        print(f"{sem}:")
        for c in cs:
            print(f"  {c.number} {c.title} ({c.type})")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for lang in LABELS:
        out = args.out_dir / f"teaching_{lang}.{args.ext}"
        out.write_text(render(semesters, people, lang), encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
