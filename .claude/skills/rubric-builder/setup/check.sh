#!/bin/bash
# check.sh - diagnose a Hebrew XeLaTeX setup on macOS (MiKTeX or MacTeX) and compile test documents.
# Read-only except for build files written to a temp folder.
# Run:  bash check.sh [path to a LaTeX repo with preamble/UnitPreamble.tex, optional]
# Exit code 0 = everything passed, 1 = something failed (details printed).
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${1:-}"
failed=0
ok()   { printf '[ OK ] %s\n' "$*"; }
bad()  { printf '[FAIL] %s\n' "$*"; failed=$((failed+1)); }
info() { printf '[info] %s\n' "$*"; }

# Fresh installs put the binaries where this shell may not look yet.
for d in "$HOME/bin" /usr/local/bin /opt/homebrew/bin "/Applications/MiKTeX Console.app/Contents/bin" /Library/TeX/texbin; do
  [ -d "$d" ] && PATH="$PATH:$d"
done
export PATH

if ! command -v xelatex >/dev/null 2>&1; then bad "xelatex not found"; exit 1; fi
ok "xelatex: $(xelatex --version 2>/dev/null | head -1) ($(command -v xelatex))"
IS_MIKTEX=0
xelatex --version 2>/dev/null | head -1 | grep -q MiKTeX && IS_MIKTEX=1

if [ $IS_MIKTEX = 1 ]; then
  auto="$(initexmf --show-config-value='[MPM]AutoInstall' 2>/dev/null)"
  if [ "$auto" = "1" ]; then ok "MiKTeX AutoInstall=1"
  else bad "MiKTeX AutoInstall is '$auto' (needs 1). Fix: initexmf --set-config-value '[MPM]AutoInstall=1'"; fi
fi

# TeX Live's XeTeX on macOS finds fonts by name only in the system font folders; MiKTeX
# may also find them in its own tree. Only a hint: the test compile decides.
if ls "$HOME/Library/Fonts"/DavidCLM-* /Library/Fonts/DavidCLM-* >/dev/null 2>&1; then
  ok "David CLM installed in Library/Fonts"
else
  info "David CLM is not in ~/Library/Fonts; if the compile below fails on this font, run install-mac.sh (it copies the Culmus fonts there)"
fi

if latexmk --version >/dev/null 2>&1; then ok "$(latexmk --version | grep -m1 Version)"
else bad "latexmk does not run"; fi

compile() { # $1 = .tex path, $2 = label
  local tex="$1" name out
  name="$(basename "$tex" .tex)"
  out="${TMPDIR:-/tmp}/hebrew-latex-check-$name"
  rm -rf "$out"; mkdir -p "$out"
  ( cd "$(dirname "$tex")" && latexmk -xelatex -interaction=nonstopmode -file-line-error -outdir="$out" "$(basename "$tex")" >"$out/latexmk-console.txt" 2>&1 )
  local errs=""
  [ -f "$out/$name.log" ] && errs="$(grep -E '^(! |.*\.(tex|sty|cls|def|cfg):[0-9]+: )' "$out/$name.log" | head -5)"
  if [ -f "$out/$name.pdf" ] && [ -z "$errs" ]; then ok "$2 compiles: $out/$name.pdf"
  else
    bad "$2 did not compile cleanly (build folder: $out)"
    [ -n "$errs" ] && printf '       %s\n' "$errs"
    [ -f "$out/$name.log" ] || echo "       no .log produced; see $out/latexmk-console.txt"
  fi
}

compile "$SKILL_DIR/hebrew-smoke-test.tex" "smoke test"
if [ -z "$REPO_DIR" ] && [ -f "./preamble/UnitPreamble.tex" ]; then REPO_DIR="$(pwd)"; fi
if [ -n "$REPO_DIR" ]; then
  for doc in exercises/04-linear-systems.tex lecture-notes/03-matrices.tex; do
    if [ -f "$REPO_DIR/$doc" ]; then compile "$REPO_DIR/$doc" "course document $doc"; else info "skipped $doc"; fi
  done
else info "course repo not given, only the smoke test was compiled"; fi

if [ $failed = 0 ]; then echo; echo "ALL CHECKS PASSED"; exit 0; fi
echo; echo "$failed CHECK(S) FAILED"; exit 1
