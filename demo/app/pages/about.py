import streamlit as st

from demo.app import ui

st.title("Research and Engineering Contributions")

st.markdown(
    """
##### Scientific design
- **Annotation as a falsifiable claim.** Each call is a typed claim (*detected* / *not detected*) whose status —
  supported, weakened, unresolved or rejected — is set by a registered falsification attack plan, not by a similarity
  threshold alone.
- **Separation of authority.** Deterministic tools produce every measurement; a language-model planner and critic may
  only choose among registered follow-up tests; a deterministic validator assigns the final claim. Provenance records
  whether any model text entered a claim.
- **Exact biological endpoints.** tet(A)/tet(B) family identity (not "any MFS transporter") and full-length rpoB
  orthology (not a domain-only hit), checked against competing protein families.

##### Evaluation discipline
- Pre-registered protocol, frozen code (commit and scientific-core hash), and a held-out 60-genome benchmark with truth
  adjudicated independently of the systems under test.
- Three arms that share one scientific core and differ only in follow-up policy (deterministic, agentic, exhaustive),
  so the agent's contribution can be isolated.
- Reporting of negative and uncomfortable findings: no accuracy gain from the agent, a constant baseline that matches
  accuracy, a degenerate tet(A) sensitivity of 0/7, a comparator parser bug found after unblinding, and a role-swap
  study in which giving the final decision to a frontier model reduced accuracy.

##### Engineering
- Typed Python package (Pydantic models), integrations with BLAST+, HMMER, MMseqs2, DIAMOND and AMRFinderPlus, a local
  Ollama model (qwen3:4b), and hash-locked per-case records for every benchmark run.
- This demo reads those locked records through a provenance-tracked bundle (source SHA256 for every input file) and
  runs live analyses in an isolated, time-limited subprocess with sanitised input.
"""
)

st.divider()
st.subheader("Author")
with st.container(border=True):
    st.markdown(
        """
**Aritra Sinha**
PhD Researcher in Food & Nutritional Sciences
University College Cork, Ireland

Research focus: microbial biology, bioinformatics, protein science, AI-assisted scientific workflows and
computational research.
"""
    )
    c = st.columns(3)
    c[0].markdown("GitHub: *link to be added*")
    c[1].markdown("LinkedIn: *link to be added*")
    c[2].markdown("Research profile: *link to be added*")

c = st.columns(2)
c[0].link_button("View Source Code", ui.REPO_URL, icon=":material/code:", width="stretch")
c[1].link_button("Explore Benchmark Results", ui.BENCHMARK_URL, icon=":material/dataset:", width="stretch")

st.divider()
st.subheader("Data sources and attribution")
st.markdown(
    """
- Genome assemblies: NCBI RefSeq (public); identified by accession throughout. Two small assemblies are bundled as
  live-analysis examples.
- Curated protein family members: public UniProt/RefSeq protein records listed in the family definitions of the source
  repository.
- Specialist comparators: NCBI AMRFinderPlus 4.2.7 (database 2026-08-07.1) and NCBI RefSeq/PGAP annotations.
"""
)
with st.expander("Bundle provenance manifest"):
    m = ui.bundle_json("BUNDLE_MANIFEST.json")
    st.json({k: v for k, v in m.items() if k != "sources"}, expanded=True)
    st.caption(f"{len(m.get('sources', []))} source files are listed with SHA256 hashes in the full manifest.")
