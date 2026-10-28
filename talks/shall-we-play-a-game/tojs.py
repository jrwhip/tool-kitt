#!/usr/bin/env python3
"""Rebuild the .js twin of every replays/*.json (record.py does this automatically)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import write_js
for j in sorted((Path(__file__).resolve().parent / "replays").glob("*.json")):
    write_js(j, json.loads(j.read_text()))
    print("wrote", j.with_suffix(".js").name)
