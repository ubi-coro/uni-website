# uni-website

Generated content for the Kollaborative Robotik pages on uni-bielefeld.de.

A GitHub Action (`.github/workflows/pages.yml`) runs the generators nightly and on every push, and publishes the output to https://ubi-coro.github.io/uni-website/. The CMS pulls each file in server-side with an RXML block containing only an insert tag, e.g.:

```html
<insert cached-href="https://ubi-coro.github.io/uni-website/teaching_de.html" fetch-interval="15 min" quote="none"/>
```

Use `cached-href`, not `href`. With plain `<insert href>`, Roxen fetches during page rendering; when a fetch fails it inserts nothing and then serves that empty page from its RAM cache, so content vanished at random. `cached-href` keeps a copy in Roxen's database, refreshed in the background every `fetch-interval`, and pages always render from that copy.

A failed or empty build fails the workflow and nothing is deployed, so the live pages keep the last good version. Changes reach the live pages within about 15 minutes of a successful deploy (the `fetch-interval`). To rebuild right away, run the workflow manually (Actions → Build pages → Run workflow).

## Teaching

`generate_teaching.py` collects the group's courses from eKVV (team = members of the PEVZ org page, see `ORG_ID` in `common.py`) and renders them as CMS accordions with lecturer cards.

- `teaching_de.html`, `teaching_en.html`

Tuning: the constants at the top of the script — `EXTRA_PERSON_IDS` for people not on the org page, `FIRST_SEMESTER`, `COURSE_TYPES`, `EXCLUDE_TITLE_PREFIXES`, and `EXCLUDE_COURSE_IDS` for single courses to hide.

## Team

`generate_team.py` renders `team.yaml` in two layouts, per language:

- `team_<lang>_grid.html`: everyone as a square photo grid (up to 4 columns), ordered by section as listed in `team.yaml`, then by surname. Hovering a photo, or tapping it on a phone, fades in the faculty accent color with name, position, e-mail, phone, room and a link to the person's profile. Template: `templates/team_grid.html`.
- `team_<lang>_profiles.html`: every profile (photo, contact details, profile links, intro, supervisor) on one page. CSS `:target` shows only the one named in the URL hash, e.g. `…/team/profil/#lara-bergmann`, so a new person needs no CMS work. The slug is the name without titles, in lowercase ASCII. Template: `templates/team_profiles.html`.
- `team_<lang>_<section>.html`, e.g. `team_de_staff.html`: the older contact cards, one file per section because their headings live in the CMS. They're still built so the team page can switch back. Template: `templates/team_section.html`.

CMS setup for the grid: on the team page, one RXML block inserting `team_de_grid.html` / `team_en_grid.html`. The CMS page `team/profil/` (`PROFILE_PAGE` in `generate_team.py`) has one RXML block inserting `team_de_profiles.html` / `team_en_profiles.html`; hide that page from the navigation. Both languages share every URL (the `/<en>/` prefix only switches the language), so the same links work on both.

To change the team, edit `team.yaml` (the GitHub web editor is fine); the site updates within about 15 minutes of the commit. People with a `pevz` id get phone and room from PEVZ, so those stay current without edits; set them in `team.yaml` only where PEVZ lacks them or is wrong. E-mail addresses always live in `team.yaml`: PEVZ protects addresses against harvesting, so the generators never scrape them. The teaching page takes lecturers' addresses from `team.yaml` too; external lecturers get none, only the PEVZ button. Anyone on the PEVZ org page who is missing from `team.yaml` shows up as a warning on the workflow run. Optional per-person extras: `intro` (a short self-introduction, `{de: …, en: …}`; a single language is shown on both pages), `supervisor` (partner-institution supervisor for joint doctorates), `position` (overrides the section's label from `POSITIONS` in `generate_team.py`) and `sortname` (the surname to sort by when it isn't the last word, e.g. `Meyer zu Theenhausen`). In an intro, a line break becomes `<br/>` and a blank line starts a new paragraph; write it as a YAML block (`de: |` followed by indented lines) or use `\n` inside double quotes. HTML in the text is escaped. To change a design, edit its template.

Adding a section means adding it to `team.yaml` and giving it a position label in `POSITIONS`; for the old card layout, also create a matching CMS section with an RXML block that inserts its file.

## Local run

```sh
uv run generate_teaching.py --out-dir out
uv run generate_team.py --out-dir out
```

## CMS quirks the markup works around

- Inside an RXML block, `.ubf-ugc dt { display: block }` overrides the accordion's flex layout, so each toggler carries `style="display: flex;"`.
- The page's `#triangle-right` SVG sprite isn't reliably present, so the icon is an inline path.
- The AsyncPicture script doesn't process inserted images, so they carry `ubf-js-loaded` to escape the site's hide-until-loaded rule.
- The site sets `html { font-size: 62.5% }`, so 1rem is 10px; the grid and profile styles size things in em (relative to the 16px body text) instead.
- The theme paints a white content background over anything not stacked above it; CMS sections escape that via `.ubf-section__content { position: relative; z-index: 2 }`. The grid and profile wrappers set the same, so an RXML block placed outside a section isn't rendered blank.
- `body` has `hyphens: auto`, which would hyphenate e-mail addresses in narrow tiles; the contact rows turn it off.
