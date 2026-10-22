# Deploying the Genome Skeptic demo

Nothing in this repository has been deployed or pushed. The steps below are a plan; each "verify" step must be
checked by a person after deployment.

## What the app needs

| Mode | Needs |
|---|---|
| Research Showcase (default) | Python ≥ 3.11 and `requirements-demo.txt`. Reads `demo/results/` only. |
| Live Analysis, deterministic/exhaustive arms | Additionally `blastn`, `tblastn`, `makeblastdb`, `hmmbuild`, `hmmsearch` on `PATH`; `mmseqs` and `diamond` optional. About 0.1–0.9 GB RAM and 15–60 s per 1–2 Mb genome (measured in WSL, 4 CPUs). |
| Live Analysis, agentic arm | Additionally `GS_DEMO_AGENTIC_BASE_URL` set to an OpenAI-compatible endpoint serving `qwen3:4b`. Not recommended for a public deployment. |

If the tools are missing, the Live Analysis page says so and offers no substitute engine.

## Local run

```bash
pip install -r requirements-demo.txt
streamlit run streamlit_app.py
python -m pytest tests/demo        # 49 tests
```

On Windows the showcase works natively; live mode needs the tools, e.g. inside WSL with the
`genome-skeptic-prod` environment on `PATH`.

## Streamlit Community Cloud (planned, not verified)

1. Push the `demo/streamlit-showcase` branch (requires the repository owner's approval) and confirm the repository
   is meant to be public.
2. Create an app: main file `streamlit_app.py`, Python 3.11 or 3.12.
3. `packages.txt` installs `ncbi-blast+` and `hmmer` via apt. MMseqs2 and DIAMOND are not installed by it; the
   pipeline records the follow-up tests that need them as unavailable. **Unverified:** apt package availability,
   memory headroom, and runtime on the hosted image.
4. To publish the showcase only, set the secret/env `GS_DEMO_DISABLE_LIVE=1`.
5. Do not set `GS_DEMO_AGENTIC_BASE_URL` on a public deployment unless you accept that derived measurement
   summaries from user uploads are sent to that endpoint.

Verify after deployment: the Overview loads; Annotation Results shows 60 cases; the Live Analysis page either
reports the tool versions or states that live mode is unavailable; an example assembly run reproduces the locked
claim shown in the comparison table.

## Scientific-core caveat

The frozen M60 system is commit `8f66868` (scientific-core hash `22ff045c…`, computed on Windows CRLF files). The
current branch includes later V5 validator changes to `locus_reconstruction.py` and
`diagnostic_needs_v4_1_dev.py`. The Live Analysis page compares the deployed files with the frozen per-file hashes,
ignoring line-ending differences, and lists every differing file. Live results are therefore labelled as
coming from deployed code, not from the frozen benchmark system. Both example assemblies reproduced their locked
GS-Deterministic claims with the current committed code.

## Security and data handling

- Upload limit of 15 MB, 15 Mb of total sequence and 5,000 records. Accepts plain ASCII nucleotide FASTA only; protein,
  gzip and binary input are rejected.
- Headers are replaced by `contig_N` before analysis, so header text cannot reach a model.
- Each run uses a fresh temporary directory that is deleted afterwards. One job runs at a time. The worker is started with an
  argument list (no shell) and a wall-clock limit, and environment variables ending in `_KEY`, `_TOKEN` or `_SECRET`
  are removed from its environment.
- Errors shown to users are one-line messages; `client.showErrorDetails = "none"` hides stack traces.
- `.streamlit/secrets.toml` is gitignored. No API keys are needed for the showcase.

## Rebuilding the results bundle

`python demo/scripts/build_demo_bundle.py` (original workstation only; needs the gitignored
`manuscript_benchmark/RUNS/`). It never modifies source records and asserts the frozen commit and core hash.
