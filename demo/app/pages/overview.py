import streamlit as st

from demo.app import ui

st.title("Genome Skeptic")
st.markdown("*Evidence-Grounded Agentic AI for Bacterial Genome Annotation*")

st.markdown(
    """
Automated annotation pipelines often label a gene from a single similarity hit. Genome Skeptic treats every
annotation as a **claim that must survive attempts to disprove it**. Deterministic bioinformatics tools
(BLAST+, HMMER, MMseqs2, DIAMOND) produce measurements. A language-model planner and critic may choose which
registered follow-up test to run next. A **deterministic validator** — not the language model — issues the
final claim, after running a falsification attack plan.

The benchmark question is narrow and exact: *is a specific gene orthologue present in a given bacterial
assembly?* Two targets were evaluated: the tetracycline efflux pump **tet(A)/tet(B)** and RNA polymerase
subunit beta (**rpoB**).
"""
)

if not ui.guard_bundle():
    st.stop()

st.subheader("How a claim is produced")
st.graphviz_chart(
    """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#1f5f7a", fillcolor="#eef5f8"];
  edge [color="#555555", fontname="Helvetica", fontsize=9];
  A [label="Bacterial assembly\\n(FASTA) + target gene"];
  M [label="Initial measurements\\nBLAST+ · HMMER · MMseqs2\\ncurated family members", fillcolor="#e8f5e9", color="#2e7d32"];
  N [label="Open diagnostic needs\\n+ ranked registered actions", fillcolor="#f3f3f3", color="#666666"];
  P [label="LLM planner\\nchooses one follow-up", fillcolor="#f1ecfa", color="#6a1b9a"];
  T [label="Registered tool runs\\n(new measurements)", fillcolor="#e8f5e9", color="#2e7d32"];
  C [label="LLM critic\\naccept / challenge", fillcolor="#fff3e0", color="#e65100"];
  V [label="Deterministic validator\\nfalsification attack plan", fillcolor="#fdecea", color="#c62828"];
  O [label="Claim\\nsupported · weakened ·\\nunresolved · rejected"];
  A -> M -> N -> P -> T -> C;
  C -> T [label="challenge:\\none extra test", style=dashed];
  C -> V [label="accept"];
  N -> V [label="no-LLM arms:\\nfixed policy", style=dotted];
  V -> O;
}
""",
    width="stretch",
)
st.caption(
    "Green: deterministic measurements · Purple/orange: language-model choices (they select tests, never "
    "measurements or the verdict) · Red: deterministic decision."
)

st.subheader("What the frozen benchmark found")
st.markdown(
    """
On the pre-registered **M60** benchmark (60 public RefSeq assemblies, 41 with independently resolved truth),
all three Genome Skeptic arms reached **33/41** correct. This is better than a conventional ≥80%-identity homology
baseline (20/41), and comparable to specialist annotation tools (34/41).
"""
)
c = st.columns(4)
c[0].metric("GS-Agentic correct", "33 / 41", help="Wilson 95% CI 0.660–0.898")
c[1].metric("Conventional baseline", "20 / 41", help="Wilson 95% CI 0.343–0.635")
c[2].metric("Follow-up tests: agentic vs exhaustive", "61 vs 189", help="67.7% fewer follow-up analyses")
c[3].metric("Median runtime: agentic vs exhaustive", "207 s vs 19 s", help="Local 4B model inference dominates")

st.warning(
    """
**Honest reading of the results**

- The language-model agent changed **no** final answers relative to the deterministic arm (0 corrections, 0 degradations).
  Its measured benefit is efficiency in follow-up tests, not accuracy — and it was *slower* in wall-clock time.
- A trivial constant per-target rule also scores 34/41 on this cohort, so accuracy alone does not show biological skill.
- For tet(A)/tet(B), every Genome Skeptic arm predicted *absent* in all 30 cases: sensitivity 0/7. Post-hoc analysis
  traced this to frozen family-state rules.
- 19 of 60 cases had unresolvable truth and are excluded from accuracy, and rpoB had no resolved negative cases.
- When a frontier model was made the final judge (role-swap study), accuracy fell from 18/20 to 11/20.
""",
    icon=":material/warning:",
)

st.subheader("Explore")
cols = st.columns(3)
with cols[0]:
    st.page_link("demo/app/pages/case_explorer.py", label="Annotation results for all 60 cases", icon=":material/table_view:")
    st.page_link("demo/app/pages/engine.py", label="Step through one case inside the engine", icon=":material/account_tree:")
with cols[1]:
    st.page_link("demo/app/pages/evidence.py", label="Inspect the biological evidence", icon=":material/biotech:")
    st.page_link("demo/app/pages/benchmarks.py", label="Benchmarks, statistics and limitations", icon=":material/monitoring:")
with cols[2]:
    st.page_link("demo/app/pages/live.py", label="Live analysis (where tools are installed)", icon=":material/play_circle:")
    st.page_link("demo/app/pages/about.py", label="Contributions and author", icon=":material/person:")

st.subheader("Curated examples")
for e in ui.examples():
    with st.container(border=True):
        st.markdown(f"**{e['title']}** · *{e['category']}* · case #{e['position']:02d}")
        st.write(e["why"])
        if st.button("Open this case", key=f"open_{e['id']}", icon=":material/arrow_forward:"):
            st.session_state["case_position"] = e["position"]
            st.switch_page("demo/app/pages/engine.py")

ui.computational_notice()
