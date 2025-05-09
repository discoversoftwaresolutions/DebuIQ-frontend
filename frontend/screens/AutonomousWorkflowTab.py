# Begin generation of new Streamlit dashboard tab for Autonomous Workflow Orchestration
streamlit_autonomous_tab = '''
import streamlit as st
import requests
import json

BACKEND_URL = st.session_state.get("BACKEND_URL", "https://debugiq-backend.onrender.com")

TRIAGE_URL = f"{BACKEND_URL}/workflow/triage"
RUN_WORKFLOW_URL = f"{BACKEND_URL}/workflow/run"
DIAGNOSE_URL = f"{BACKEND_URL}/workflow/diagnose"
VALIDATE_URL = f"{BACKEND_URL}/workflow/validate"
CREATE_PR_URL = f"{BACKEND_URL}/workflow/create-pr"

st.subheader("🧠 Autonomous Workflow Orchestration")

st.markdown("Use this panel to trigger any part of the DebugIQ agent workflow or run the full end-to-end fix pipeline.")

# --- Upload raw issue input for triage ---
st.markdown("### 📨 Ingest New Issue")

uploaded_issue_file = st.file_uploader("Upload raw issue JSON (e.g. trace or monitoring event)", type=["json"])
if uploaded_issue_file:
    raw_json = json.load(uploaded_issue_file)
    if st.button("🚀 Triage with AI"):
        with st.spinner("Triage in progress..."):
            resp = requests.post(TRIAGE_URL, json={"raw_data": raw_json})
            st.json(resp.json())

# --- Run full workflow ---
st.markdown("### ⚙️ Run Full Workflow")
issue_id_full = st.text_input("Issue ID to fully auto-fix", key="workflow_full_id")
if st.button("Run Full AI Workflow"):
    resp = requests.post(RUN_WORKFLOW_URL, json={"issue_id": issue_id_full})
    st.json(resp.json())

# --- Modular Controls ---
st.markdown("### 🛠️ Manual Agent Controls")

issue_id = st.text_input("Issue ID", key="manual_issue_id")
patch_diff = st.text_area("Paste Patch Diff for Validation", key="manual_patch_diff")

cols = st.columns(3)

with cols[0]:
    if st.button("🔬 Diagnose"):
        r = requests.post(DIAGNOSE_URL, json={"issue_id": issue_id})
        st.json(r.json())

with cols[1]:
    if st.button("✅ Validate Patch"):
        r = requests.post(VALIDATE_URL, json={"issue_id": issue_id, "patch_diff_content": patch_diff})
        st.json(r.json())

with cols[2]:
    if st.button("📤 Create PR"):
        r = requests.post(CREATE_PR_URL, json={"issue_id": issue_id})
        st.json(r.json())
'''.strip()

# Write this tab screen to a standalone file
autonomous_tab_path = Path("/mnt/data/DebugIQ-frontend/frontend/screens/AutonomousWorkflowTab.py")
autonomous_tab_path.parent.mkdir(parents=True, exist_ok=True)
autonomous_tab_path.write_text(streamlit_autonomous_tab + "\n")

autonomous_tab_path
