"""Import human outcome labels from a spreadsheet CSV (same rules as POST /api/admin/labels).

  python scripts/import_labels.py --export-queue queue.csv   # template: experiment_id, notes, suggested_label, label, quote, labelled_by
  python scripts/import_labels.py labels.csv                 # columns: experiment_id,label,quote,labelled_by  (rows with empty label are skipped)

label in: sustained_burn | brief_then_self_extinguished | no_ignition | extinguished_by_flow_or_N2 | hardware_issue | unclear
quote must be a verbatim span of the record's flame_behavior_notes.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import labels  # noqa: E402

if len(sys.argv) == 3 and sys.argv[1] == "--export-queue":
    q = labels.queue("pending", limit=1000)
    with open(sys.argv[2], "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["experiment_id", "oxygen_pct", "pressure_kpa", "flame_behavior_notes", "suggested_label (hint only)", "suggested_quote", "label", "quote", "labelled_by"])
        for i in q.items:
            w.writerow([i.experiment_id, i.oxygen_pct, i.pressure_kpa, i.flame_behavior_notes, i.suggested_label or "", i.suggested_quote or "", "", "", ""])
    print(f"wrote {len(q.items)} rows to {sys.argv[2]}")
elif len(sys.argv) == 2:
    r = labels.import_csv(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    print(f"imported {r['imported']} labels")
    for e in r["errors"]:
        print(f"  line {e['line']} {e['experiment_id']}: {e['error']}")
    sys.exit(1 if r["errors"] else 0)
else:
    sys.exit(__doc__)
