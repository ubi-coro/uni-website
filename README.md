# uni-website

Generated content for the Kollaborative Robotik pages on uni-bielefeld.de.

## Teaching pages

`generate_teaching.py` collects the group's courses from eKVV (team = members of the PEVZ org page, see `ORG_ID`) and renders them as CMS accordions with lecturer cards, in German and English. A GitHub Action runs it nightly and publishes the result to GitHub Pages:

- https://ubi-coro.github.io/uni-website/teaching_de.html
- https://ubi-coro.github.io/uni-website/teaching_en.html

The CMS pulls these in server-side. Each teaching page has an RXML block containing only:

```html
<insert href="https://ubi-coro.github.io/uni-website/teaching_de.html" quote="none"/>
```

A failed or empty scrape fails the workflow and nothing is deployed, so the live page keeps the last good version. To refresh right away, run the workflow manually (Actions → Teaching pages → Run workflow).

### Local run

```sh
uv run generate_teaching.py --out-dir out
```

### Tuning

Edit the constants at the top of the script: `EXTRA_PERSON_IDS` for people not on the org page, `FIRST_SEMESTER`, `COURSE_TYPES`, `EXCLUDE_TITLE_PREFIXES`, and `EXCLUDE_COURSE_IDS` for single courses to hide.

### CMS quirks the markup works around

- Inside an RXML block, `.ubf-ugc dt { display: block }` overrides the accordion's flex layout, so each toggler carries `style="display: flex;"`.
- The page's `#triangle-right` SVG sprite isn't reliably present, so the icon is an inline path.
- The AsyncPicture script doesn't process these images, so they carry `ubf-js-loaded` to escape the site's hide-until-loaded rule.
