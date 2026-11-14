"""Build data/derived/validation.json + validation_report.md from the confirmed labels. Run: python scripts/build_validation.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import validation  # noqa: E402

v = validation.write_files()
o, c = v.old_method_test, v.correction_model
print(f"labels confirmed: {v.labels_confirmed}/{v.labels_total_needed}")
print(f"old method: evaluated={o['n_evaluated']} burn_below_MOC={o['n_burn_below_moc']} nonburn_above_MOC={o['n_nonburn_above_moc']}")
print(f"saffire pairs: {len(v.saffire_pairs)}; correction model: {c['status']} (n_pairs={c['n_pairs']})")
print("wrote data/derived/validation.json and validation_report.md")
