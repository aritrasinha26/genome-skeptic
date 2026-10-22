import streamlit as st

from demo.app import ui
from demo.app.services import trace_model as tm

st.title("Inside the Annotation Engine")
ui.precomputed_banner()
if not ui.guard_bundle():
    st.stop()

st.markdown(
    "Each step below is reconstructed from the recorded provenance of one locked run. Steps are labelled by "
    "who produced them: **raw biological evidence** from deterministic tools, **model-generated interpretation** "
    "from the language-model planner, **critic assessment**, and the **final system decision** made by the "
    "deterministic validator. Hidden model reasoning was not recorded and is not shown; only the short "
    "rationales the models returned as part of their structured output are displayed."
)

trace = ui.case_picker("engine_case")
arm = st.segmented_control(
    "Arm",
    list(tm.ARM_LABELS),
    default="GS_AGENTIC_V4_1",
    format_func=lambda a: tm.ARM_LABELS[a].split(" (")[0],
    key="engine_arm",
) or "GS_AGENTIC_V4_1"
st.caption(tm.ARM_LABELS[arm])
ui.case_header(trace)

expand = st.toggle("Expand all recorded details", value=False)
ui.render_engine_steps(tm.engine_steps(trace, arm), expand_all=expand)

st.markdown("##### Final claim")
ui.render_claim_card(trace["arms"][arm].get("claim"))

prov = trace["arms"][arm].get("provenance") or {}
with st.expander("Integrity checks recorded for this run"):
    st.json(
        {
            "validator_consumed_final_measurements": prov.get("validator_consumed_measurement_hash") is not None,
            "measurements_changed_before_validation": prov.get("measurements_changed_before_validation"),
            "llm_measurement_entered_claim": prov.get("llm_measurement_entered_claim"),
            "planner_grounding_status": prov.get("planner_grounding_status"),
            "model_call_count": prov.get("model_call_count"),
            "frozen_system": trace.get("frozen_system"),
        },
        expanded=True,
    )
ui.computational_notice()
