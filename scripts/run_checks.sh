#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/build_pokemon_dataset.py

echo "[OK] py_compile: scripts/build_pokemon_dataset.py"
