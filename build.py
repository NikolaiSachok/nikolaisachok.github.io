#!/usr/bin/env python3
"""Generate the per-locale pages of nikolaisachok.com.

    python3 build.py            # write the pages
    python3 build.py --check    # fail if the committed pages are stale

Sources: template.html + content/<lang>.json + assets/style.css.
Outputs: index.html (English) and <lang>/index.html for every other locale.

Standard library only, no build dependencies. The generated HTML is committed,
because GitHub Pages serves this repo as-is with no CI step.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = "https://nikolaisachok.com"

# --- locale registry --------------------------------------------------------
# Order here is the order of the language switcher and of the hreflang block.
LOCALES = [
    # code, <html lang>, og:locale, path under the domain
    ("en", "en", "en_US", "/"),
    ("de", "de", "de_DE", "/de/"),
    ("sk", "sk", "sk_SK", "/sk/"),
    ("ru", "ru", "ru_RU", "/ru/"),
]
CODES = [c for c, _, _, _ in LOCALES]
SOURCE_LOCALE = "en"  # English is the source of truth; x-default points at it

# Links live here, not in the content files: translators never touch a URL, and
# a link change is a one-line edit in one place. Each list matches its array in
# every content/<lang>.json positionally.
#
# Writing and projects are two lists because they are two kinds of thing. They
# render with identical markup and differ only by the section they sit under —
# which is the whole design: the reader tells them apart by grouping and by the
# date, never by a different container shape.
WRITING_LINKS = [
    # Standing work first, dated pieces after — the ordinary shape of a
    # publication index. The handbook lives here rather than under projects
    # because it is prose; with it moved, PROJECT_LINKS is three repositories
    # and the English label "Built" no longer has to stretch over a docs site.
    "https://nikolaisachok.com/ai-engineering-handbook/",
    # Always the canonical address, never a syndicated copy: this page indexes
    # the work, it does not host or mirror it.
    "https://dev.to/nsachok/eval-first-rag-use-separate-scores-to-triage-failures-33ed",
]

PROJECT_LINKS = [
    # Root-relative because this one is a page of THIS site, not a sibling
    # project site: the hub keeps the reader, and the case page hands off to the
    # repository. Every other link here leaves for somewhere the work lives.
    "/work/strata-rag/",
    "https://github.com/NikolaiSachok/strata-insurance-corpus",
    "https://nikolaisachok.com/DC-plugins/",
]

# --- case pages -------------------------------------------------------------
# Long-form records for one project: what was decided, and what the work taught.
# ENGLISH ONLY, deliberately. The home page is localised because it is the front
# door and a visitor should meet it in their own language; a decision record is
# read by engineers evaluating the work, in English, and translating it would
# multiply every future edit by four for no reader. The handbook already
# established that locale scope is per artifact rather than per site.
CASES = [
    # slug (also the path under /work/)
    "strata-rag",
]
CASE_ROOT = "work"


REQUIRED_KEYS = {
    "meta": ["title", "description", "og_title", "og_description"],
    "switcher": ["label", "names"],
    "theme": ["label", "names"],
    "notice": ["text", "english_link", "dismiss"],
    "header": ["name", "role", "lead_1", "lead_2"],
    "video": ["section_label", "play_label", "img_alt", "iframe_title", "caption"],
    "sections": ["work", "writing", "built"],
}

# --- escaping ---------------------------------------------------------------
# Content strings are trusted HTML fragments: a few of them carry <em>/<strong>
# on purpose. So tags are passed through, and only bare ampersands are repaired
# — that is the one thing an author (or a translator) reliably gets wrong.
_BARE_AMP = re.compile(r"&(?!#?[A-Za-z0-9]+;)")


def html(text: str) -> str:
    """Inline content destined for the document body."""
    return _BARE_AMP.sub("&amp;", text)


def attr(text: str) -> str:
    """Plain text destined for an attribute value (aria-label, meta content)."""
    return (
        _BARE_AMP.sub("&amp;", text)
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# --- fragment builders ------------------------------------------------------
def style_href() -> str:
    """`/assets/style.css?v=<content hash>` — a URL that changes when the CSS does.

    The domain sits behind Cloudflare, which caches stylesheets at the edge for
    four hours (`cache-control: max-age=14400`) while HTML passes through
    uncached (`cf-cache-status: DYNAMIC`). Without this, a CSS-only change is
    invisible to visitors for hours and a hard refresh cannot help them: the
    browser re-requests the same URL and the edge answers from its copy.

    Hashing the content sidesteps every cache at once, because a URL nobody has
    requested cannot be a stale hit. It also makes `--check` catch a CSS edit
    that was never rebuilt: the hash moves, so the committed pages go stale.
    """
    digest = hashlib.sha256((ROOT / "assets" / "style.css").read_bytes()).hexdigest()
    return f"/assets/style.css?v={digest[:12]}"


def hreflang_block(indent: str = "  ") -> str:
    lines = [
        f'{indent}<link rel="alternate" hreflang="{code}" href="{SITE}{path}" />'
        for code, _, _, path in LOCALES
    ]
    default = dict((c, p) for c, _, _, p in LOCALES)[SOURCE_LOCALE]
    lines.append(f'{indent}<link rel="alternate" hreflang="x-default" href="{SITE}{default}" />')
    return "\n".join(lines)


def og_locale_alt(current: str, indent: str = "  ") -> str:
    return "\n".join(
        f'{indent}<meta property="og:locale:alternate" content="{og}" />'
        for code, _, og, _ in LOCALES
        if code != current
    )


def langbar(current: str, names: dict, indent: str = "      ") -> str:
    parts = []
    for i, (code, lang, _, path) in enumerate(LOCALES):
        if i:
            parts.append(f'{indent}<span class="sep" aria-hidden="true">·</span>')
        mark = ' aria-current="page"' if code == current else ""
        label = attr(names.get(code, code.upper()))
        parts.append(
            f'{indent}<a href="{path}" hreflang="{lang}" lang="{lang}" '
            f'data-setlang="{code}" aria-label="{label}"{mark}>{code.upper()}</a>'
        )
    return "\n".join(parts)


# Stroke icons on one 24-unit grid, one visual style, sized and coloured by CSS.
# All three ship in the markup and CSS reveals whichever matches the current
# data-theme — so the glyph is correct at first paint, with no script to swap it
# and no flash of the wrong one. The half-filled disc is the conventional
# "follows the system" mark.
THEME_ICONS = {
    "light": (
        '<circle cx="12" cy="12" r="4" />'
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2'
        'M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />'
    ),
    "dark": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />',
    "auto": '<circle cx="12" cy="12" r="9" /><path class="icon-fill" d="M12 3a9 9 0 0 0 0 18z" />',
}


def themebar(names: dict, label: str, indent: str = "      ") -> str:
    """One button that cycles auto -> light -> dark -> auto.

    A single control instead of three: three uppercase words beside four
    language codes made the bar heavier than the name below it.

    The cost of cycling is that the other states are not visible, so the label
    carries the weight — title for a hover tooltip, aria-label for assistive
    tech, both naming the CURRENT state and both localised. The translated words
    stay useful here; an icon alone would have thrown them away.
    """
    svgs = "\n".join(
        f'{indent}  <svg class="icon-{key}" viewBox="0 0 24 24" aria-hidden="true">{paths}</svg>'
        for key, paths in THEME_ICONS.items()
    )
    data = " ".join(f'data-name-{key}="{attr(names[key])}"' for key in THEME_ICONS)
    return (
        f'{indent}<button type="button" id="theme-toggle" data-label="{attr(label)}" {data}\n'
        f'{indent}        title="{attr(label)}: {attr(names["auto"])}"\n'
        f'{indent}        aria-label="{attr(label)}: {attr(names["auto"])}">\n'
        f"{svgs}\n"
        f"{indent}</button>"
    )


def notice_block(current: str, notice: dict, indent: str = "    ") -> str:
    """The 'we picked your browser's language' banner.

    Rendered into every non-English page but hidden by CSS; the head script
    reveals it (before paint) only when this page was reached by detection.
    """
    if current == SOURCE_LOCALE:
        return ""
    en_path = dict((c, p) for c, _, _, p in LOCALES)[SOURCE_LOCALE]
    return (
        f'{indent}<div class="notice" role="status">\n'
        f'{indent}  <span class="notice-text">{html(notice["text"])} '
        f'<a href="{en_path}" hreflang="en" lang="en" data-setlang="en">'
        f'{html(notice["english_link"])}</a></span>\n'
        f'{indent}  <button type="button" class="notice-dismiss" '
        f'aria-label="{attr(notice["dismiss"])}">&times;</button>\n'
        f"{indent}</div>\n"
    )


def tags_block(tags: list, indent: str = "      ") -> str:
    """One dot-separated line rather than a row of boxes.

    The separator lives INSIDE the <li> because only <li> may be a child of
    <ul>, and the list is worth keeping: a screen reader announcing "list, 7
    items" is more use than a paragraph. It is aria-hidden, like the separators
    in the language bar and the header contact links — same house pattern.
    """
    out = []
    for i, tag in enumerate(tags):
        sep = "" if i == 0 else '<span class="sep" aria-hidden="true">·</span>'
        out.append(f'{indent}<li class="tag">{sep}{html(tag)}</li>')
    return "\n".join(out)


def entries_block(items: list, links: list, name: str, indent: str = "      ") -> str:
    """One renderer for both lists — writing and projects share their markup.

    The reader separates them by which section they sit under and by the meta
    line, not by a different container: that is the point of the design. Giving
    each list its own markup would let the two drift apart again.
    """
    if len(items) != len(links):
        raise SystemExit(
            f"content has {len(items)} '{name}' entries but build.py defines {len(links)} links"
        )
    out = []
    for item, href in zip(items, links):
        out.append(
            f"{indent}<li>\n"
            f'{indent}  <a class="entry" href="{href}">\n'
            f'{indent}    <span class="entry-title">{html(item["title"])}</span>\n'
            f'{indent}    <span class="entry-desc">{html(item["desc"])}</span>\n'
            f'{indent}    <span class="entry-meta">{html(item["meta"])}</span>\n'
            f"{indent}  </a>\n"
            f"{indent}</li>"
        )
    return "\n".join(out)


def project_links_block(links: list, indent: str = "        ") -> str:
    """The case page's outbound links, in the header's contact-link shape.

    Same markup and separators as the home page's identity line, because they do
    the same job in the same position: a small chrome cluster that says where to
    go next before the reading starts.
    """
    parts = []
    for i, link in enumerate(links):
        if i:
            parts.append(f'{indent}<span class="sep" aria-hidden="true">·</span>')
        parts.append(f'{indent}<a href="{link["href"]}">{html(link["label"])}</a>')
    return "\n".join(parts)


def head_script(current: str, indent: str = "  ") -> str:
    """Language detection / preference routing. Inline and synchronous so it
    runs before first paint — no flash of the wrong language, no flash of the
    notice.

    Rules, in order:
      1. ?lang=<code> always wins and is stored as the preference.
      2. A stored preference wins over detection and is never overridden.
      3. navigator.languages is only consulted on the English root; a visitor
         who opened /de/ directly meant it.
      4. location.replace(), so Back never bounces the visitor into a loop.
    Every branch is wrapped in try/catch: with JS off or storage blocked the
    page simply stays as served, which is the correct fallback.
    """
    body = """
(function () {
  var HERE = '%(here)s';
  var ALL = %(all)s;
  try {
    var store = null;
    try { store = window.localStorage; } catch (e) {}

    /* Theme first, and before any redirect below can return: an explicit choice
       has to be on <html> before first paint, or the page flashes the other
       palette. No stored choice means no attribute, which leaves the stylesheet
       following prefers-color-scheme. data-js reveals the control, which would
       otherwise be a dead button for anyone without scripting. */
    var theme = null;
    if (store) { try { theme = store.getItem('nls-theme'); } catch (e) {} }
    if (theme === 'light' || theme === 'dark') {
      document.documentElement.setAttribute('data-theme', theme);
    }
    document.documentElement.setAttribute('data-js', '');
    var params = new URLSearchParams(location.search);
    var forced = (params.get('lang') || '').toLowerCase().split('-')[0];
    var target = null, auto = false;

    if (ALL.indexOf(forced) > -1) {
      target = forced;
      if (store) { try { store.setItem('nls-lang', forced); } catch (e) {} }
    } else if (HERE === '%(source)s') {
      var saved = null;
      if (store) { try { saved = store.getItem('nls-lang'); } catch (e) {} }
      if (saved && ALL.indexOf(saved) > -1) {
        target = saved;
      } else if (!saved) {
        var pref = (navigator.languages && navigator.languages.length)
          ? navigator.languages : [navigator.language || ''];
        for (var i = 0; i < pref.length; i++) {
          var p = String(pref[i] || '').toLowerCase().split('-')[0];
          if (p === '%(source)s') break;
          if (ALL.indexOf(p) > 0) { target = p; auto = true; break; }
        }
      }
    }

    if (target && target !== HERE) {
      params.delete('lang');
      var qs = params.toString();
      if (auto) { try { sessionStorage.setItem('nls-auto', target); } catch (e) {} }
      location.replace(%(paths)s[target] + (qs ? '?' + qs : '') + location.hash);
      return;
    }

    /* Already on the right page: drop ?lang= so the address bar stays clean
       and crawlers never see a second URL for the same content. */
    if (params.has('lang')) {
      params.delete('lang');
      var rest = params.toString();
      try {
        history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash);
      } catch (e) {}
    }

    try {
      if (sessionStorage.getItem('nls-auto') === HERE) {
        sessionStorage.removeItem('nls-auto');
        document.documentElement.setAttribute('data-autolang', '');
      }
    } catch (e) {}
  } catch (e) {}
})();
""" % {
        "here": current,
        "all": json.dumps(CODES),
        "source": SOURCE_LOCALE,
        "paths": json.dumps({c: p for c, _, _, p in LOCALES}),
    }
    body = "\n".join(indent + line if line else "" for line in body.strip("\n").split("\n"))
    return f"{indent}<script>\n{body}\n{indent}</script>"


def body_block(blocks: list, indent: str = "      ") -> str:
    """The article body: headings and paragraphs, nothing else.

    Deliberately not a markdown renderer. The source article is converted to
    these blocks once, on the way in, so the site keeps its no-dependency rule
    and the page cannot acquire structures the stylesheet has never seen.
    Inline emphasis, code and links arrive as HTML fragments, which is what the
    content files have always carried.

    An h2 here takes no class, so it does NOT pick up the home page's
    .section-head: that rule sets a one-word category label in 0.7rem uppercase
    sans, which is right for "Writing" and unreadable for a ten-word sentence.
    An article subhead is a statement and is set as one.
    """
    out = []
    for block in blocks:
        tag = block["type"]
        out.append(f'{indent}<{tag}>{html(block["text"])}</{tag}>')
    return "\n".join(out)


def case_head_script(indent: str = "  ") -> str:
    """Theme only — no language routing.

    The home page's head script may redirect a visitor to their own locale. A
    case page has one locale, so the same script would either do nothing or,
    worse, bounce a reader off the page they asked for and onto a localised home
    page. What remains is the part that must still run before first paint:
    applying a stored theme so the page never flashes the other palette, and
    setting data-js so the theme control exists only where it can work.
    """
    body = """
(function () {
  try {
    var theme = null;
    try { theme = window.localStorage.getItem('nls-theme'); } catch (e) {}
    if (theme === 'light' || theme === 'dark') {
      document.documentElement.setAttribute('data-theme', theme);
    }
    document.documentElement.setAttribute('data-js', '');
  } catch (e) {}
})();
"""
    body = "\n".join(indent + line if line else "" for line in body.strip("\n").split("\n"))
    return f"{indent}<script>\n{body}\n{indent}</script>"


# --- page assembly ----------------------------------------------------------
def validate_case(slug: str, data: dict) -> None:
    """A case file is checked as strictly as a locale file."""
    where = f"content/cases/{slug}.json"
    for section, keys in (
        ("meta", ("title", "description", "og_title", "og_description")),
        ("project", ("name", "deck", "role", "links")),
    ):
        if section not in data:
            raise SystemExit(f"{where}: missing section '{section}'")
        for key in keys:
            if key not in data[section]:
                raise SystemExit(f"{where}: missing '{section}.{key}'")
    for key in ("kicker", "body"):
        if key not in data:
            raise SystemExit(f"{where}: missing '{key}'")
    for i, link in enumerate(data["project"]["links"]):
        for key in ("label", "href"):
            if key not in link:
                raise SystemExit(f"{where}: 'project.links[{i}]' is missing '{key}'")
    if not data["body"]:
        raise SystemExit(f"{where}: 'body' is empty")
    for i, block in enumerate(data["body"]):
        for key in ("type", "text"):
            if key not in block:
                raise SystemExit(f"{where}: 'body[{i}]' is missing '{key}'")
        if block["type"] not in ("h2", "p"):
            raise SystemExit(
                f"{where}: 'body[{i}]' has type '{block['type']}', expected 'h2' or 'p'"
            )
        # An unbalanced fragment silently eats the rest of the page, and the
        # article legitimately contains angle brackets inside code spans.
        if block["text"].count("<") != block["text"].count(">"):
            raise SystemExit(f"{where}: 'body[{i}]' has unbalanced angle brackets")


def render_case(slug: str, template: str) -> str:
    data = json.loads((ROOT / "content" / "cases" / f"{slug}.json").read_text(encoding="utf-8"))
    validate_case(slug, data)
    meta, project = data["meta"], data["project"]

    # The theme control's labels are not localised here the way they are on the
    # home page: this page is English, so it takes the English words directly.
    theme_names = {"light": "Light", "dark": "Dark", "auto": "Auto"}
    theme_label = "Colour theme"

    subs = {
        "TITLE": html(meta["title"]),
        "DESCRIPTION": attr(meta["description"]),
        "CANONICAL": f"{SITE}/{CASE_ROOT}/{slug}/",
        "OG_TITLE": attr(meta["og_title"]),
        "OG_DESCRIPTION": attr(meta["og_description"]),
        "STYLE_HREF": style_href(),
        "HEAD_SCRIPT": case_head_script(),
        "THEME_LABEL": attr(theme_label),
        "THEMEBAR": themebar(theme_names, theme_label),
        "KICKER": html(data["kicker"]),
        "PROJECT_NAME": html(project["name"]),
        "PROJECT_DECK": html(project["deck"]),
        "PROJECT_ROLE": html(project["role"]),
        "PROJECT_LINKS": project_links_block(project["links"]),
        "BODY": body_block(data["body"]),
    }

    out = template
    for key, value in subs.items():
        out = out.replace("{{%s}}" % key, value)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        raise SystemExit(f"case {slug}: unsubstituted placeholders {sorted(set(left))}")
    return out


def validate(code: str, data: dict) -> None:
    for section, keys in REQUIRED_KEYS.items():
        if section not in data:
            raise SystemExit(f"content/{code}.json: missing section '{section}'")
        for key in keys:
            if key not in data[section]:
                raise SystemExit(f"content/{code}.json: missing '{section}.{key}'")
    # themebar() indexes these directly, so a missing one should fail here with
    # a useful message rather than as a KeyError mid-render.
    for key in ("light", "dark", "auto"):
        if key not in data["theme"]["names"]:
            raise SystemExit(f"content/{code}.json: missing 'theme.names.{key}'")
    for name, expect in (
        ("tags", 7),
        ("writing", len(WRITING_LINKS)),
        ("cards", len(PROJECT_LINKS)),
    ):
        got = len(data.get(name, []))
        if got != expect:
            raise SystemExit(f"content/{code}.json: '{name}' has {got} items, expected {expect}")
    # Every entry carries a meta line. A writing entry's date lives there as a
    # locale-formatted string rather than being computed: only the translator
    # knows how a date is written in their language.
    for name in ("writing", "cards"):
        for i, item in enumerate(data.get(name, [])):
            for key in ("title", "desc", "meta"):
                if key not in item:
                    raise SystemExit(f"content/{code}.json: '{name}[{i}]' is missing '{key}'")


def render(code: str, lang: str, og: str, path: str, template: str) -> str:
    data = json.loads((ROOT / "content" / f"{code}.json").read_text(encoding="utf-8"))
    validate(code, data)
    meta, video, sections = data["meta"], data["video"], data["sections"]

    subs = {
        "LANG": lang,
        "TITLE": html(meta["title"]),
        "DESCRIPTION": attr(meta["description"]),
        "CANONICAL": f"{SITE}{path}",
        "HREFLANG": hreflang_block(),
        "OG_TITLE": attr(meta["og_title"]),
        "OG_DESCRIPTION": attr(meta["og_description"]),
        "OG_LOCALE": og,
        "OG_LOCALE_ALT": og_locale_alt(code),
        "STYLE_HREF": style_href(),
        "HEAD_SCRIPT": head_script(code),
        "SWITCHER_LABEL": attr(data["switcher"]["label"]),
        "LANGBAR": langbar(code, data["switcher"]["names"]),
        "THEME_LABEL": attr(data["theme"]["label"]),
        "THEMEBAR": themebar(data["theme"]["names"], data["theme"]["label"]),
        "NOTICE": notice_block(code, data["notice"]),
        "NAME": html(data["header"]["name"]),
        "ROLE": html(data["header"]["role"]),
        "LEAD_1": html(data["header"]["lead_1"]),
        "LEAD_2": html(data["header"]["lead_2"]),
        "VIDEO_SECTION_LABEL": attr(video["section_label"]),
        "VIDEO_PLAY_LABEL": attr(video["play_label"]),
        "VIDEO_IFRAME_TITLE": attr(video["iframe_title"]),
        "VIDEO_IMG_ALT": attr(video["img_alt"]),
        "VIDEO_CAPTION": html(video["caption"]),
        "H2_WORK": html(sections["work"]),
        "H2_WRITING": html(sections["writing"]),
        "H2_BUILT": html(sections["built"]),
        "TAGS": tags_block(data["tags"]),
        "WRITING": entries_block(data["writing"], WRITING_LINKS, "writing"),
        "BUILT": entries_block(data["cards"], PROJECT_LINKS, "cards"),
    }

    out = template
    for key, value in subs.items():
        out = out.replace("{{%s}}" % key, value)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        raise SystemExit(f"{code}: unsubstituted placeholders {sorted(set(left))}")
    return out


def main() -> int:
    check = "--check" in sys.argv[1:]
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    case_template = (ROOT / "case.html").read_text(encoding="utf-8")
    stale = []

    pages = [
        (
            ROOT / "index.html" if path == "/" else ROOT / path.strip("/") / "index.html",
            lambda code=code, lang=lang, og=og, path=path: render(code, lang, og, path, template),
        )
        for code, lang, og, path in LOCALES
    ] + [
        (
            ROOT / CASE_ROOT / slug / "index.html",
            lambda slug=slug: render_case(slug, case_template),
        )
        for slug in CASES
    ]

    for target, build in pages:
        page = build()
        if check:
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current != page:
                stale.append(str(target.relative_to(ROOT)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)}")
    if check:
        if stale:
            print("stale (run: python3 build.py): " + ", ".join(stale), file=sys.stderr)
            return 1
        print("all pages up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
