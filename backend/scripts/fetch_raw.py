"""Download / verify the raw primary-source files listed in data/raw/MANIFEST.json (sha256-checked).

  python backend/scripts/fetch_raw.py            # download anything missing, then verify all
  python backend/scripts/fetch_raw.py --verify   # verify only (no network)
Files are untrusted downloads: they are only stored and parsed, never executed.
"""
import hashlib, json, sys, urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
man = json.loads((RAW / "MANIFEST.json").read_text())["files"]
verify_only = "--verify" in sys.argv
bad = 0
for m in man:
    p = RAW / m["file"]
    if not p.exists() and not verify_only:
        p.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(m["url"], headers={"User-Agent": "research-data-fetch/1.0"}), timeout=120) as r:
            p.write_bytes(r.read())
    ok = p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == m["sha256"]
    bad += not ok
    print(("OK      " if ok else "MISMATCH" if p.exists() else "MISSING ") + m["file"])
sys.exit(1 if bad else 0)
