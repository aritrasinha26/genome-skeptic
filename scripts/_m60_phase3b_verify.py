#!/usr/bin/env python3
from pathlib import Path
import hashlib, csv, json
from collections import Counter

root = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/manuscript_benchmark/TRUTH_M60")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

orig_t = sha(root / "M60_EXTERNAL_TRUTH_LOCKED.json")
orig_m = sha(root / "M60_TRUTH_LOCK_MANIFEST.json")
fin_t = sha(root / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json")
fin_m = sha(root / "M60_TRUTH_FINAL_LOCK_MANIFEST.json")
print("orig_truth", orig_t, "MATCH" if orig_t == "bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38" else "FAIL")
print("orig_lock", orig_m, "MATCH" if orig_m == "f6636498de4f7ebc61b50fc85a5a1f48065100b27bfb5eda29e712249fe8c491" else "FAIL")
print("final_truth", fin_t)
print("final_lock", fin_m)
print("adj", sha(root / "M60_HUMAN_ADJUDICATION.csv"))
print("case", sha(root / "M60_TRUTH_FINAL_CASE_LEVEL.csv"))
print("rev", sha(root / "M60_TRUTH_FINAL_REVIEW.csv"))

hr = root / "HUMAN_REVIEW"
js = sorted(hr.glob("position_*.json"))
md = sorted(hr.glob("position_*.md"))
print("packets json", len(js), "md", len(md))

with open(root / "M60_HUMAN_ADJUDICATION.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
print("adj n", len(rows))
print("changed", [(r["position"], r["pre_review_truth"], r["human_review_truth"]) for r in rows if r["changed_yes_no"] == "yes"])

final = json.loads((root / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json").read_text(encoding="utf-8"))
print("final n", len(final["cases"]), final["kind"])
print("pred opened", final["prediction_payloads_opened"], "d20", final["d20_touched"], "acc", final["accuracy_scored"])
print("truth", dict(Counter(x["truth_value"] for x in final["cases"])))
print("teta", dict(Counter(x["truth_value"] for x in final["cases"] if x["target"].startswith("tetA"))))
print("rpob", dict(Counter(x["truth_value"] for x in final["cases"] if x["target"].startswith("rpoB"))))

blob = (root / "M60_HUMAN_ADJUDICATION.csv").read_text(encoding="utf-8").lower()
for tok in ["amrfinder", "pgap", "gs_agentic", "claims.json", "d20"]:
    print("adj leak", tok, tok in blob)
leaks = []
for p in js:
    t = p.read_text(encoding="utf-8").lower()
    for tok in ["amrfinder", "pgap", "gs_agentic", "gs_deterministic", "claims.json"]:
        if tok in t:
            leaks.append((p.name, tok))
print("packet leaks", leaks)
print("original overwritten", orig_t != "bb37539060efd3e89e0bd548fe1d0e573991dab0816bdead729286cbfcfedb38")
