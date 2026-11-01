#!/usr/bin/env bash
# One-step setup for test-data-gen: installs Python, ffmpeg, LibreOffice and zip if they are missing,
# creates .venv and installs the Python packages. Safe to run again.
# Run it with:  bash setup.sh   (no file permissions needed)
# Supports macOS (Homebrew) and Debian/Ubuntu (apt). On Windows use WSL (Ubuntu) and run this inside it.
set -euo pipefail
cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }
say() { printf '\n==> %s\n' "$*"; }
python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
find_python() {
  local c
  for c in python3.13 python3.12 python3.11 python3.10 python3 "$(brew --prefix 2>/dev/null || true)/bin/python3"; do
    if have "$c" && python_ok "$c"; then command -v "$c"; return 0; fi
  done
  return 1
}
have_soffice() { have soffice || have libreoffice || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; }

OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
  if ! have brew; then
    echo "Homebrew is needed to install the tools. Install it from https://brew.sh, then run ./setup.sh again."
    exit 1
  fi
  say "Checking tools (macOS, Homebrew)"
  find_python >/dev/null || { say "Installing Python"; brew install python; }
  have ffmpeg || { say "Installing ffmpeg"; brew install ffmpeg; }
  have_soffice || { say "Installing LibreOffice (large download)"; brew install --cask libreoffice; }
elif [ "$OS" = "Linux" ] && have apt-get; then
  say "Checking tools (Debian/Ubuntu)"
  need=()
  find_python >/dev/null && python3 -c 'import venv, ensurepip' >/dev/null 2>&1 || need+=(python3 python3-venv python3-pip)
  have ffmpeg || need+=(ffmpeg)
  have_soffice || need+=(libreoffice)
  have zip || need+=(zip)
  if [ "${#need[@]}" -gt 0 ]; then
    say "Installing: ${need[*]}"
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO apt-get update
    $SUDO apt-get install -y "${need[@]}"
  fi
else
  echo "Unsupported system. Install these yourself, then see the README:"
  echo "  Python 3.10+, ffmpeg, LibreOffice, zip"
  exit 1
fi

PY="$(find_python)" || { echo "Python 3.10 or newer was not found after installing. Open a new terminal and run ./setup.sh again."; exit 1; }
say "Creating .venv with $("$PY" --version)"
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
say "Installing Python packages"
.venv/bin/python -m pip install --quiet -r requirements.txt

say "Checking ffmpeg encoders"
missing=0
for enc in libx264 libx265 libvpx-vp9 libmp3lame libopus; do
  if ! ffmpeg -hide_banner -encoders 2>/dev/null | grep -q " $enc "; then
    echo "warning: your ffmpeg has no $enc encoder, so some video or audio files will print FAIL"
    missing=1
  fi
done
[ "$OS" = "Darwin" ] || echo "note: HEIC images need macOS (sips), so those files will print FAIL here. Everything else is built."

say "Ready. Build the files with:"
echo "  source .venv/bin/activate"
echo "  python generate.py"
