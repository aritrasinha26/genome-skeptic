#!/usr/bin/env python3
from d12_common import EXPECTED_V3_FREEZE, assert_d20_untouched, blocked_accessions_and_genera, verify_v3_freeze

f = verify_v3_freeze()
print("FREEZE", f, flush=True)
assert_d20_untouched("preflight")
blocked, genera, note = blocked_accessions_and_genera()
print("blocked", len(blocked), "genera", len(genera), flush=True)
print("note", note, flush=True)
print("freeze_match", f["manifest_sha256"] == EXPECTED_V3_FREEZE, flush=True)
