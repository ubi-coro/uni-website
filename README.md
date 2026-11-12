# uni-website

Generated content for the Kollaborative Robotik pages on uni-bielefeld.de.

A GitHub Action (`.github/workflows/pages.yml`) runs the generators nightly and on every push, and publishes the output to https://ubi-coro.github.io/uni-website/. The CMS pulls each file in server-side with an RXML block containing only an insert tag, e.g.:

```html
<insert href="https://ubi-coro.github.io/uni-website/teaching_de.html" quote="none"/>
```

A failed or empty build fails the workflow and nothing is deployed, so the live pages keep the last good version. If a fetch fails on the CMS side, Roxen inserts nothing rather than breaking the page. To refresh right away, run the workflow manually (Actions → Build pages → Run workflow).

## Teaching

`generate_teaching.py` collects the group's courses from eKVV (team = members of the PEVZ org page, see `ORG_ID` in `common.py`) and renders them as CMS accordions with lecturer cards.

- `teaching_de.html`, `teaching_en.html`

Tuning: the constants at the top of the script — `EXTRA_PERSON_IDS` for people not on the org page, `FIRST_SEMESTER`, `COURSE_TYPES`, `EXCLUDE_TITLE_PREFIXES`, and `EXCLUDE_COURSE_IDS` for single courses to hide.

## Team

`generate_team.py` renders `team.yaml` with `templates/team_section.html`, one file per section and language, because the section headings live in the CMS:

- `team_<lang>_<section>.html`, e.g. `team_de_staff.html`, `team_en_joint.html`

To change the team, edit `team.yaml` (the GitHub web editor is fine); the site updates about a minute after the commit. People with a `pevz` id get phone and room from PEVZ, so those stay current without edits; set them in `team.yaml` only where PEVZ lacks them or is wrong. E-mail addresses always live in `team.yaml`: PEVZ protects addresses against harvesting, so the generators never scrape them. The teaching page takes lecturers' addresses from `team.yaml` too; external lecturers get none, only the PEVZ button. Anyone on the PEVZ org page who is missing from `team.yaml` shows up as a warning on the workflow run. To change the card design, edit the template.

Adding a section means adding it to `team.yaml` and creating a matching CMS section with an RXML block that inserts its file.

## Local run

```sh
uv run generate_teaching.py --out-dir out
uv run generate_team.py --out-dir out
```

## CMS quirks the markup works around

- Inside an RXML block, `.ubf-ugc dt { display: block }` overrides the accordion's flex layout, so each toggler carries `style="display: flex;"`.
- The page's `#triangle-right` SVG sprite isn't reliably present, so the icon is an inline path.
- The AsyncPicture script doesn't process inserted images, so they carry `ubf-js-loaded` to escape the site's hide-until-loaded rule.
