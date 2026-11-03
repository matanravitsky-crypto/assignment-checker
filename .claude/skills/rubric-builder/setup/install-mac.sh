#!/bin/bash
# install-mac.sh - install MiKTeX (or MacTeX with --mactex) + everything needed to compile the
# Hebrew XeLaTeX rubric, then run check.sh. Safe to run again.
# Needs Homebrew (https://brew.sh). No sudo for the MiKTeX route.
# Run:  bash install-mac.sh [--mactex] [--no-update] [--vscode] [path to a LaTeX repo, optional]
#   --mactex     install MacTeX (TeX Live, about 6 GB) instead of MiKTeX; use if MiKTeX fails
#   --no-update  skip updating every installed MiKTeX package
#   --vscode     also install the LaTeX Workshop extension for VS Code
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$SCRIPTS"
MACTEX=0; NOUPDATE=0; VSCODE=0; REPO_DIR=""
for a in "$@"; do
  case "$a" in
    --mactex) MACTEX=1 ;;
    --no-update) NOUPDATE=1 ;;
    --vscode) VSCODE=1 ;;
    *) REPO_DIR="$a" ;;
  esac
done
step() { printf '\n=== %s\n' "$*"; }
die()  { printf 'STOPPED: %s\n' "$*"; exit 1; }

for d in "$HOME/bin" /usr/local/bin /opt/homebrew/bin "/Applications/MiKTeX Console.app/Contents/bin" /Library/TeX/texbin; do
  [ -d "$d" ] && PATH="$PATH:$d"
done
export PATH
command -v brew >/dev/null 2>&1 || die "Homebrew is missing. The user must install it from https://brew.sh (it asks for their password), then run this script again."

step "0. Python 3"
command -v python3 >/dev/null 2>&1 || brew install python
python3 -m pip install -q pymupdf pillow mammoth || python3 -m pip install -q --break-system-packages pymupdf pillow mammoth

step "1. TeX distribution"
if command -v xelatex >/dev/null 2>&1; then
  echo "Already installed: $(xelatex --version | head -1)"
elif [ $MACTEX = 1 ]; then
  brew install --cask mactex-no-gui || die "MacTeX did not install"
  PATH="$PATH:/Library/TeX/texbin"
else
  brew install --cask miktex-console || die "MiKTeX did not install. Try again with --mactex."
  MB="/Applications/MiKTeX Console.app/Contents/bin"
  "$MB/miktexsetup" finish || die "'miktexsetup finish' failed. Try again with --mactex."
  PATH="$PATH:$HOME/bin:$MB"
fi
command -v xelatex >/dev/null 2>&1 || die "xelatex still not found after installing."
IS_MIKTEX=0
xelatex --version | head -1 | grep -q MiKTeX && IS_MIKTEX=1

if [ $IS_MIKTEX = 1 ]; then
  step "2. MiKTeX: automatic package installation, updates, course packages"
  initexmf --set-config-value '[MPM]AutoInstall=1'
  miktex packages update-package-database
  [ $NOUPDATE = 1 ] || miktex packages update || miktex packages update
  miktex packages require --package-id-file "$SKILL_DIR/packages.txt"
  initexmf --update-fndb
else
  step "2. TeX Live: checking the course packages"
  missing=""
  for f in polyglossia.sty bidi.sty fontspec.sty tcolorbox.sty textpos.sty braket.sty needspace.sty fontawesome5.sty adforn.sty DavidCLM-Medium.otf latexmk.pl; do
    kpsewhich "$f" >/dev/null 2>&1 || missing="$missing $f"
  done
  if [ -n "$missing" ]; then
    echo "Missing:$missing"
    echo "The user must run (asks for their password):"
    echo "  sudo tlmgr update --self && sudo tlmgr install culmus polyglossia bidi tcolorbox textpos braket needspace fontawesome5 adforn latexmk"
  fi
fi

step "3. Culmus Hebrew fonts into ~/Library/Fonts (XeTeX on macOS finds fonts by name only there)"
mkdir -p "$HOME/Library/Fonts"
for probe in DavidCLM-Medium.otf MiriamCLM-Book.ttf; do
  p="$(kpsewhich "$probe" 2>/dev/null)"
  if [ -n "$p" ]; then
    cp -n "$(dirname "$p")"/*CLM* "$HOME/Library/Fonts/" 2>/dev/null
    echo "copied fonts from $(dirname "$p")"
  else
    echo "WARNING: $probe not found in the TeX tree (is the culmus package installed?)"
  fi
done

if [ $VSCODE = 1 ] && command -v code >/dev/null 2>&1; then
  step "4. VS Code LaTeX Workshop"
  code --install-extension James-Yu.latex-workshop
fi

step "Verifying"
bash "$SCRIPTS/check.sh" "$REPO_DIR"
rc=$?
if [ -x "$HOME/bin/xelatex" ] && ! grep -q 'HOME/bin' "$HOME/.zprofile" 2>/dev/null; then
  echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.zprofile"
  echo "Added ~/bin to PATH in ~/.zprofile."
fi
echo "Open a NEW terminal (and restart VS Code) so that xelatex and latexmk are on PATH there."
exit $rc
