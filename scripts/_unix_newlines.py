from pathlib import Path
root = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor")
for rel in (
    "scripts/run_fast_pilot.sh",
    "scripts/_kill_leftover_production.sh",
    "scripts/_retry_fast_pilot_pao1.sh",
    "scripts/_run_fast_pilot_heldout.sh",
):
    p = root / rel
    if p.exists():
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        print("unix", rel)
