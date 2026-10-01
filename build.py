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
# Open source and writing share one list: standing work first, then articles in
# order of relevance to a buyer (the RAG piece before the niche security one).
# Articles always link to the canonical address, never a syndicated copy.
PUBLIC_LINKS = [
    "https://nikolaisachok.com/ai-engineering-handbook/",
    "https://nikolaisachok.com/Strata-RAG/",
    "https://github.com/NikolaiSachok/strata-insurance-corpus",
    "https://dev.to/nsachok/eval-first-rag-use-separate-scores-to-triage-failures-33ed",
    "https://dev.to/nsachok/i-asked-a-frontier-llm-to-recover-secrets-from-my-decompiled-build-1ojb",
]

# One per case study, positionally; None means the case has no public page
# (client work stays unlinked by design).
CASE_LINKS = [
    None,
    None,
    "https://github.com/NikolaiSachok/redmine",
]

# Fixed shape of the page: the layout is designed around these counts, so a
# locale that drifts from them fails the build instead of rendering lopsided.
COUNTS = {"proof": 4, "help": 4, "cases": len(CASE_LINKS), "process": 4, "public": len(PUBLIC_LINKS)}

REQUIRED_KEYS = {
    "meta": ["title", "description", "og_title", "og_description"],
    "switcher": ["label", "names"],
    "theme": ["label", "names"],
    "notice": ["text", "english_link", "dismiss"],
    "hero": ["availability", "name", "role", "photo_alt", "headline", "lead",
             "cta_email", "cta_video", "location"],
    "video": ["dialog_label", "iframe_title", "close"],
    "sections": ["help", "cases", "process", "public", "about", "skills"],
    "labels": ["problem", "did", "result", "details", "read"],
    "cta": ["title", "text", "email", "linkedin"],
    "footer": ["copy"],
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


def chips_block(items: list, indent: str = "        ") -> str:
    """Skills as chips. Each chip is its own box, so wrapping never strands a
    separator at the start of a line (the defect of the old dot-joined list)."""
    return "\n".join(f'{indent}<li>{html(s)}</li>' for s in items)


def proof_block(items: list, indent: str = "      ") -> str:
    return "\n".join(
        f'{indent}<li><span class="proof-num">{html(p["num"])}</span>'
        f'<span class="proof-label">{html(p["label"])}</span></li>'
        for p in items
    )


def help_block(items: list, indent: str = "        ") -> str:
    out = []
    for h in items:
        out.append(
            f"{indent}<li>\n"
            f'{indent}  <h3>{html(h["title"])}</h3>\n'
            f'{indent}  <p>{html(h["desc"])}</p>\n'
            f'{indent}  <p class="fit">{html(h["fit"])}</p>\n'
            f"{indent}</li>"
        )
    return "\n".join(out)


def cases_block(items: list, labels: dict, indent: str = "      ") -> str:
    """Each case reads problem -> what I did -> result: the shape a buyer scans
    for, with the result row set apart so it can be found without reading.

    The engineering specifics (services, vendors, counts) live in a collapsed
    <details> under the case: there for the reader who wants them, out of the
    way of the one who is deciding whether this person can help."""
    out = []
    for case, href in zip(items, CASE_LINKS):
        more = (
            f'{indent}  <details class="case-more">\n'
            f'{indent}    <summary>{html(labels["details"])}</summary>\n'
            f'{indent}    <p>{html(case["details"])}</p>\n'
            f"{indent}  </details>\n"
        )
        link = (
            f'{indent}  <a class="case-link" href="{href}">{html(labels["read"])} '
            f'<span aria-hidden="true">→</span></a>\n'
            if href
            else ""
        )
        out.append(
            f'{indent}<article class="case">\n'
            f'{indent}  <p class="kicker">{html(case["kicker"])}</p>\n'
            f'{indent}  <h3>{html(case["title"])}</h3>\n'
            f'{indent}  <dl>\n'
            f'{indent}    <div><dt>{html(labels["problem"])}</dt><dd>{html(case["problem"])}</dd></div>\n'
            f'{indent}    <div><dt>{html(labels["did"])}</dt><dd>{html(case["did"])}</dd></div>\n'
            f'{indent}    <div class="result"><dt>{html(labels["result"])}</dt><dd>{html(case["result"])}</dd></div>\n'
            f"{indent}  </dl>\n"
            f"{more}"
            f"{link}"
            f"{indent}</article>"
        )
    return "\n".join(out)


def steps_block(items: list, indent: str = "        ") -> str:
    return "\n".join(
        f'{indent}<li><h3>{html(s["title"])}</h3><p>{html(s["desc"])}</p></li>' for s in items
    )


def about_block(paras: list, indent: str = "      ") -> str:
    return "\n".join(f"{indent}<p>{html(p)}</p>" for p in paras)


def entries_block(items: list, links: list, indent: str = "        ") -> str:
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


# --- page assembly ----------------------------------------------------------
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
    for name, expect in COUNTS.items():
        got = len(data.get(name, []))
        if got != expect:
            raise SystemExit(f"content/{code}.json: '{name}' has {got} items, expected {expect}")
    for key in ("about", "skills", "help_intro"):
        if not data.get(key):
            raise SystemExit(f"content/{code}.json: '{key}' must be non-empty")
    # A date lives in an entry's meta line as a locale-formatted string rather
    # than being computed: only the translator knows how a date is written.
    item_keys = {
        "proof": ("num", "label"),
        "help": ("title", "desc", "fit"),
        "cases": ("kicker", "title", "problem", "did", "result", "details"),
        "process": ("title", "desc"),
        "public": ("title", "desc", "meta"),
    }
    for name, keys in item_keys.items():
        for i, item in enumerate(data[name]):
            for key in keys:
                if key not in item:
                    raise SystemExit(f"content/{code}.json: '{name}[{i}]' is missing '{key}'")


def render(code: str, lang: str, og: str, path: str, template: str) -> str:
    data = json.loads((ROOT / "content" / f"{code}.json").read_text(encoding="utf-8"))
    validate(code, data)
    meta, video, sections, hero, cta = (
        data["meta"], data["video"], data["sections"], data["hero"], data["cta"]
    )

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
        "AVAILABILITY": html(hero["availability"]),
        "NAME": html(hero["name"]),
        "ROLE": html(hero["role"]),
        "PHOTO_ALT": attr(hero["photo_alt"]),
        "HEADLINE": html(hero["headline"]),
        "LEAD": html(hero["lead"]),
        "CTA_EMAIL": html(hero["cta_email"]),
        "CTA_VIDEO": html(hero["cta_video"]),
        "LOCATION": html(hero["location"]),
        "VIDEO_DIALOG_LABEL": attr(video["dialog_label"]),
        "VIDEO_IFRAME_TITLE": attr(video["iframe_title"]),
        "VIDEO_CLOSE": attr(video["close"]),
        "PROOF": proof_block(data["proof"]),
        "H2_HELP": html(sections["help"]),
        "HELP_INTRO": html(data["help_intro"]),
        "HELP": help_block(data["help"]),
        "H2_CASES": html(sections["cases"]),
        "CASES": cases_block(data["cases"], data["labels"]),
        "H2_PROCESS": html(sections["process"]),
        "STEPS": steps_block(data["process"]),
        "H2_PUBLIC": html(sections["public"]),
        "PUBLIC": entries_block(data["public"], PUBLIC_LINKS),
        "H2_ABOUT": html(sections["about"]),
        "ABOUT": about_block(data["about"]),
        "H3_SKILLS": html(sections["skills"]),
        "SKILLS": chips_block(data["skills"]),
        "CTA_TITLE": html(cta["title"]),
        "CTA_TEXT": html(cta["text"]),
        "CTA_EMAIL_2": html(cta["email"]),
        "CTA_LINKEDIN": html(cta["linkedin"]),
        "FOOTER_COPY": html(data["footer"]["copy"]),
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
    stale = []
    for code, lang, og, path in LOCALES:
        page = render(code, lang, og, path, template)
        target = ROOT / "index.html" if path == "/" else ROOT / path.strip("/") / "index.html"
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
