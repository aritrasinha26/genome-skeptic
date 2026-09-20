#!/usr/bin/env bash
# Bootstrap the Genome Skeptic production bioinformatics environment.
# Canonical path: Docker. Fallback: micromamba on Linux/WSL2.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mode="${1:-auto}"

have() { command -v "$1" >/dev/null 2>&1; }

bootstrap_docker() {
  echo "Building canonical Docker image genome-skeptic-prod"
  docker build -t genome-skeptic-prod "$ROOT"
  docker run --rm genome-skeptic-prod genome-skeptic doctor --out /tmp/production_stack.json
  echo "Docker image genome-skeptic-prod is ready."
}

install_micromamba() {
  if have micromamba; then
    return
  fi
  echo "Installing micromamba into \$HOME/micromamba"
  curl -L https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj -C /tmp bin/micromamba
  mkdir -p "$HOME/micromamba/bin"
  mv /tmp/bin/micromamba "$HOME/micromamba/bin/micromamba"
  export PATH="$HOME/micromamba/bin:$PATH"
  "$HOME/micromamba/bin/micromamba" shell hook -s bash >/dev/null
}

bootstrap_micromamba() {
  install_micromamba
  export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/micromamba}"
  eval "$("$HOME/micromamba/bin/micromamba" shell hook -s bash)"
  echo "Creating conda env genome-skeptic-prod from environment.yml"
  micromamba create -y -n genome-skeptic-prod -f "$ROOT/environment.yml" || \
    micromamba install -y -n genome-skeptic-prod -f "$ROOT/environment.yml"
  micromamba run -n genome-skeptic-prod pip install -e "$ROOT"
  micromamba run -n genome-skeptic-prod python - <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, "src")
from genome_skeptic.eval.stack import write_environment_manifest
write_environment_manifest(Path("environment_manifest.json"))
print("wrote environment_manifest.json")
PY
  echo "Activate with: micromamba activate genome-skeptic-prod"
}

case "$mode" in
  docker)
    bootstrap_docker
    ;;
  micromamba|wsl|conda)
    bootstrap_micromamba
    ;;
  auto)
    if have docker; then
      bootstrap_docker
    else
      echo "Docker is not available. Using WSL2/Linux micromamba fallback."
      bootstrap_micromamba
    fi
    ;;
  *)
    echo "Usage: $0 [auto|docker|micromamba]"
    exit 2
    ;;
esac
