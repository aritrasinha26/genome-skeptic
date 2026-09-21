# Canonical production-benchmark environment for Genome Skeptic.
# Build: docker build -t genome-skeptic-prod .
# Tool versions are recorded at build time into /opt/genome-skeptic/environment_manifest.json
FROM mambaorg/micromamba:1.5.8

ARG MAMBA_DOCKERFILE_ACTIVATE=1
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl procps \
    && rm -rf /var/lib/apt/lists/*

USER $MAMBA_USER
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml \
    && micromamba clean --all --yes

COPY --chown=$MAMBA_USER:$MAMBA_USER . /opt/genome-skeptic
WORKDIR /opt/genome-skeptic
RUN micromamba run -n base pip install --no-cache-dir -e .
RUN micromamba run -n base pip install --no-cache-dir checkm2 || true
RUN micromamba run -n base python - <<'PY'
import json, os, shutil, subprocess, datetime
from pathlib import Path
tools = [
    "fastp","fastqc","spades.py","quast.py","minimap2","samtools",
    "mmseqs","diamond","hmmsearch","hmmbuild","wgsim","FastTree",
    "bakta","checkm2","kraken2","sourmash","prodigal",
]
rows = []
for name in tools:
    path = shutil.which(name)
    version = None
    if path:
        for args in ([name, "--version"], [name, "-v"], [name, "version"]):
            try:
                p = subprocess.run(args, capture_output=True, text=True, timeout=12)
                text = (p.stdout or p.stderr or "").strip().splitlines()
                if text:
                    version = text[0][:300]
                    break
            except Exception:
                continue
    rows.append({"tool": name, "path": path, "version": version})
payload = {
    "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    "image_note": "genome-skeptic-prod",
    "python": os.sys.version,
    "tools": rows,
}
Path("/opt/genome-skeptic/environment_manifest.json").write_text(json.dumps(payload, indent=2))
print("wrote environment_manifest.json")
PY

ENV GENOME_SKEPTIC_ENV=production
ENV PYTHONUNBUFFERED=1
WORKDIR /opt/genome-skeptic
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh"]
CMD ["genome-skeptic", "doctor", "--smoke", "--out", "/tmp/production_stack.json"]
