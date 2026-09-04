#!/usr/bin/env bash
# leak-check.sh — deterministic, dependency-free leak guard (the hard gate).
#
# Adapted from the same gate in Strata-RAG so the sibling public repos fail the
# same way for the same reasons. Site-specific additions: an image metadata pass
# (this repo will carry promotional screenshots) and .DS_Store.
#
# Scans for GENERIC leak tells only — real local user paths, hardcoded secrets,
# non-example emails, DO-NOT-SHIP markers, image metadata. It contains NO domain
# wordlist and never will: a checker that enumerates the sensitive terms is
# itself a leak of them. The domain pack is private and lives with the
# audit-repo-for-leaks skill, which is run before pushing content-bearing
# changes. This script is the cheap deterministic layer under that judgement
# layer, not a replacement for it.
#
# Usage:
#   scripts/leak-check.sh            # scan the STAGED diff (default; pre-commit)
#   scripts/leak-check.sh PATH       # scan a file or directory recursively (CI)
#
# Exit 0 + "clean" if nothing found; non-zero + file:line of each hit otherwise.

set -u

WORK=$(mktemp -d)
HITS="$WORK/hits"
: >"$HITS"
trap 'rm -rf "$WORK"' EXIT

# --- what we never scan ------------------------------------------------------
is_excluded() {
  case "$1" in
    # This file necessarily CONTAINS the pattern vocabulary and would self-trip.
    */scripts/leak-check.sh|scripts/leak-check.sh|./scripts/leak-check.sh) return 0 ;;
    */.git/*|.git/*|*/node_modules/*|node_modules/*)                      return 0 ;;
    */__pycache__/*|__pycache__/*)                                        return 0 ;;
  esac
  return 1
}

# --- pick a grep that understands PCRE inline flags --------------------------
if printf 'x' | grep -qP 'x' 2>/dev/null; then
  GREP_PCRE=1
else
  GREP_PCRE=0
fi

# --- the GENERIC pattern set (no domain terms) -------------------------------
# Format: "LABEL<TAB>regex". (?i) means case-insensitive for that pattern.
PATTERNS=$(printf '%s\n' \
'local-user-path	/Users/[A-Za-z0-9._-]+/' \
'local-user-path	/home/[A-Za-z0-9._-]+/' \
'windows-user-path	[Cc]:\\Users\\[^\\]+\\' \
'mounted-volume	/Volumes/[A-Za-z0-9 ._-]+/' \
'aws-access-key	(AKIA|ASIA)[0-9A-Z]{16}' \
'aws-secret-ref	(?i)aws_secret_access_key' \
'openai-key	sk-[A-Za-z0-9]{20,}' \
'anthropic-key	sk-ant-[A-Za-z0-9_-]{20,}' \
'github-token	gh[pousr]_[A-Za-z0-9]{30,}' \
'github-pat	github_pat_[A-Za-z0-9_]{20,}' \
'slack-token	xox[baprs]-[A-Za-z0-9-]{10,}' \
'google-api-key	AIza[0-9A-Za-z_-]{35}' \
'private-key-block	-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' \
'generic-secret-assign	(?i)(api[_-]?key|secret|passwd|password|token|bearer)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_./+-]{16,}' \
'db-creds-url	(postgres|postgresql|mysql|mongodb|redis)://[^[:space:]"'"'"']*:[^[:space:]"'"'"'@]+@' \
'do-not-ship	(?i)do[[:space:]_-]*not[[:space:]_-]*(ship|commit|publish)' \
)

EMAIL_RE='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

# --- image metadata ----------------------------------------------------------
# A screenshot carries more than it shows: GPS, a device serial, an owner name,
# or a description field naming the product it was captured from. Stripping the
# visible domain tells from a page does nothing about the ones inside the file.
#
# exiftool is the right tool and is not a build dependency of this repo, so when
# it is absent this pass SKIPS LOUDLY rather than silently passing — a gate that
# quietly does not run is worse than no gate, because it is trusted.
RISKY_TAGS='GPS|Serial|OwnerName|Artist|Creator|By-line|UserComment|ImageDescription|Caption|Title|Subject|Keywords|Description|Comment|HostComputer|DocumentName'

scan_image() {
  img="$1"; display="$2"
  if ! command -v exiftool >/dev/null 2>&1; then
    printf 'SKIP[image-metadata] %s (exiftool not installed — run: brew install exiftool)\n' \
      "$display" >>"$WORK/skips"
    return
  fi
  meta=$(exiftool -s -G -- "$img" 2>/dev/null | grep -iE "^\[[A-Za-z0-9]+\][[:space:]]+($RISKY_TAGS)" || true)
  if [ -n "$meta" ]; then
    printf '%s\n' "$meta" | while IFS= read -r line; do
      printf 'LEAK[image-metadata] %s: %s\n' "$display" "$line" >>"$HITS"
    done
  fi
}

is_image() {
  case "$1" in
    *.png|*.PNG|*.jpg|*.JPG|*.jpeg|*.JPEG|*.webp|*.WEBP|*.gif|*.GIF|*.tif|*.tiff|*.heic|*.HEIC) return 0 ;;
  esac
  return 1
}

# --- text scan ---------------------------------------------------------------
scan_one() {
  content_file="$1"; display="$2"; label=""; re=""; rendered=""; line=""

  printf '%s\n' "$PATTERNS" | while IFS=$'\t' read -r label re; do
    [ -z "$label" ] && continue
    if [ "$GREP_PCRE" -eq 1 ]; then
      grep -nP -- "$re" "$content_file" 2>/dev/null
    else
      rendered=$(printf '%s' "$re" | sed 's/(?i)//g')
      grep -niE -- "$rendered" "$content_file" 2>/dev/null
    fi | while IFS= read -r line; do
      printf 'LEAK[%s] %s:%s\n' "$label" "$display" "$line" >>"$HITS"
    done
  done

  # Emails: flag only a non-example, non-placeholder address.
  grep -nE -- "$EMAIL_RE" "$content_file" 2>/dev/null | while IFS= read -r line; do
    bad=$(printf '%s\n' "$line" | grep -oE -- "$EMAIL_RE" \
            | grep -ivE '@([A-Za-z0-9.-]*\.)?(example|test|invalid|localhost)(\.[a-z]+)?$|@yourdomain\.[a-z]+$' || true)
    if [ -n "$bad" ]; then
      printf 'LEAK[non-example-email] %s:%s\n' "$display" "$line" >>"$HITS"
    fi
  done
}

# --- gather targets ----------------------------------------------------------
if [ "$#" -ge 1 ]; then
  TARGET="$1"
  if [ -d "$TARGET" ]; then
    while IFS= read -r f; do
      is_excluded "$f" && continue
      if is_image "$f"; then
        scan_image "$f" "$f"
      elif grep -Iq . "$f" 2>/dev/null; then
        scan_one "$f" "$f"
      fi
    done < <(find "$TARGET" -type f 2>/dev/null)
  elif [ -f "$TARGET" ]; then
    if ! is_excluded "$TARGET"; then
      if is_image "$TARGET"; then
        scan_image "$TARGET" "$TARGET"
      elif grep -Iq . "$TARGET" 2>/dev/null; then
        scan_one "$TARGET" "$TARGET"
      fi
    fi
  else
    echo "leak-check: no such path: $TARGET" >&2
    exit 2
  fi
else
  files=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
  if [ -z "$files" ]; then
    echo "leak-check: clean (no staged files to scan)"
    exit 0
  fi
  printf '%s\n' "$files" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    is_excluded "$f" && continue
    # An image has to be read from the working tree: exiftool needs a real file
    # with its container intact, and the staged blob is what will ship, so the
    # two are only equal when the file is not modified after staging. Staged
    # content wins for text; for images we check the file on disk and say so.
    if is_image "$f"; then
      [ -f "$f" ] && scan_image "$f" "$f (working tree)"
      continue
    fi
    tmp="$WORK/staged.blob"
    if git show ":$f" >"$tmp" 2>/dev/null && grep -Iq . "$tmp" 2>/dev/null; then
      scan_one "$tmp" "$f"
    fi
  done
fi

# --- .DS_Store ---------------------------------------------------------------
if find . -name .DS_Store -not -path './.git/*' 2>/dev/null | grep -q .; then
  printf 'LEAK[ds-store] .DS_Store present — remove before committing\n' >>"$HITS"
fi

# --- verdict -----------------------------------------------------------------
if [ -s "$WORK/skips" ]; then
  echo "leak-check: WARNING — some checks did not run:" >&2
  cat "$WORK/skips" >&2
  echo "" >&2
fi

if [ -s "$HITS" ]; then
  cat "$HITS"
  echo ""
  echo "leak-check: FAIL — potential leaks found above. Remove/redact before committing."
  exit 1
fi

echo "leak-check: clean (no generic leak patterns found)"
exit 0
