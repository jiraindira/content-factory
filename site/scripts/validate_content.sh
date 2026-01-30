#!/usr/bin/env bash
set -euo pipefail

# Pass through optional args like --fix
ARGS="${*:-}"

# Run from site/, validation lives at repo root
cd ..

# Prefer python3 (common on linux), fallback to python
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

# Install minimal deps (no Poetry on Vercel)
$PY -m pip install --upgrade pip
$PY -m pip install -r requirements-vercel.txt

# Run validation
$PY validate_content.py $ARGS
