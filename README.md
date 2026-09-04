# nikolaisachok.github.io

Personal landing page — served at **https://nikolaisachok.com** (GitHub Pages user site).

Four locales: **English (source, at `/`)**, German `/de/`, Slovak `/sk/`, Russian `/ru/`.
No framework, no CDN, no dependencies — the pages are fully self-contained apart from the YouTube
thumbnail. The only tool is a stdlib-only Python 3 script.

## Layout

```
template.html        the single page skeleton — edit markup HERE, never in a generated page
content/en.json      English copy: the source of truth for every claim on the page
content/de.json      German   ┐
content/sk.json      Slovak   ├─ meaning-first translations of en.json, same key structure
content/ru.json      Russian  ┘
assets/style.css     one shared stylesheet for all four locales
build.py             generator (Python 3 stdlib only)

index.html           GENERATED — English
de/index.html        GENERATED
sk/index.html        GENERATED
ru/index.html        GENERATED
CNAME                custom domain — do not touch
.nojekyll            do not touch
```

The generated pages are **committed**: GitHub Pages serves this repo as-is, there is no CI step.

## Rebuild

```sh
python3 build.py            # regenerate all four pages
python3 build.py --check    # exit 1 if the committed pages are stale (no writes)
```

Then commit the changed `content/*.json` **and** the regenerated `*.html` together, and push to
`main`. Pages redeploys automatically.

## Editing rules

- **Never edit `index.html` or `*/index.html` by hand** — the next build overwrites it. Change
  `content/<lang>.json` (text) or `template.html` (markup) instead.
- **English is the source of truth.** Change `content/en.json` first, then bring the other three in
  line. Every factual claim on the page is verified; translations preserve claims exactly and never
  add one.
- Content strings are **HTML fragments**: `<em>` and `<strong>` are allowed and meaningful. Write a
  literal `&` — the build escapes it.
- Card **URLs** live in `build.py` (`CARD_LINKS`), not in the content files, and are matched
  positionally to the `cards` array. `build.py` refuses to build if the counts disagree.
- Adding a locale: add a row to `LOCALES` in `build.py` and a `content/<code>.json`. hreflang,
  canonical, `og:locale`, the switcher and the redirect table all derive from that one row.

## i18n behaviour

- Each locale is a real, indexable page with its own `<html lang>`, canonical, translated `<title>`
  / description / Open Graph tags, and the full set of `hreflang` alternates plus `x-default`
  (pointing at the English root).
- A visible **language switcher** (EN · DE · SK · RU) sits at the top of every page.
- **Language detection** is JS-only and lives in a small inline `<head>` script, so it runs before
  first paint and the served HTML is identical for crawlers:
  1. `?lang=<code>` always wins and is stored as the visitor's preference.
  2. A stored preference (set by `?lang=` or by clicking the switcher) wins over detection and is
     never auto-overridden.
  3. Otherwise `navigator.languages` is consulted **on the English root only** — opening `/de/`
     directly is always honoured. No match, or English first, stays on English.
  4. Redirects use `location.replace()`, so Back never bounces the visitor into a loop.
  5. A visitor routed by detection gets a small dismissible notice in that language with a one-click
     link back to English.
- With JavaScript off, every page serves its full content and all four locales stay reachable
  through the switcher. Nothing is redirected server-side and nothing is `noindex`.

## Gates

Two deterministic checks guard every change. They run in CI on every push and pull request
(`.github/workflows/checks.yml`), and locally as pre-commit hooks once installed:

```sh
pip install pre-commit && pre-commit install    # once
pre-commit run --all-files                      # on demand
```

**`scripts/leak-check.sh`** — the leak guard. Local user paths, hardcoded secrets and API keys,
private-key blocks, database credential URLs, non-example email addresses, the markers people leave in
a file to stop it shipping, `.DS_Store`, and **image metadata** (GPS, device serial, owner name, and
the description fields where
a screenshot records what it was captured from — a picture carries more than it shows).

It takes the staged diff by default and a path when given one, so the hook checks what you are about
to commit and CI checks the whole tree. The image pass needs `exiftool`; where it is missing the pass
**skips loudly** rather than passing silently, because a gate that quietly does not run is worse than
no gate — it is trusted.

It contains **no domain wordlist and never will**: a checker that enumerates sensitive terms is
itself a disclosure of them. This is the cheap deterministic layer only. Judgement about indirect
and structural leaks — a neutral-sounding field name or data model that still encodes a private
domain — belongs to a separate private audit run before publishing content-bearing changes.

**`build.py --check`** — the generated pages are committed, because GitHub Pages serves this repo
as-is with no build step. So editing `content/`, `template.html` or the stylesheet
without rebuilding ships a page that no longer matches its own source, silently, for as long as
nobody looks. This fails the build instead.
