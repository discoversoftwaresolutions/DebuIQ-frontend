# Save this code as AutonomousWorkflowTab.py (or similar) in your project's source code.
# This file contains the code for a specific tab/section of your Streamlit app.
# Your main Streamlit script (e.g., streamlit-dashboard.py) will import and use this.
# Do NOT run a separate script to write this file to /mnt/data at runtime.

import streamlit as st
import requests
import json
import os # Import os to potentially use os.getenv

# It's generally better to define BACKEND_URL once in the main app
# and pass it or store it in session_state if this is a separate module.
# Assuming it's okay to fetch it here as per your snippet:
BACKEND_URL = os.getenv("BACKEND_URL", "https://debugiq-backend.onrender.com")
# Or, if this module is always imported AFTER BACKEND_URL is set in the main app:
# BACKEND_URL = st.session_state.get("BACKEND_URL", "https://debugiq-backend.onrender.com")
# Using os.getenv is safer if this module might be loaded before session_state is fully populated.

TRIAGE_URL = f"{BACKEND_URL}/workflow/triage"
RUN_WORKFLOW_URL = f"{BACKEND_URL}/workflow/run"
DIAGNOSE_URL = f"{BACKEND_URL}/workflow/diagnose"
VALIDATE_URL = f"{BACKEND_URL}/workflow/validate"
CREATE_PR_URL = f"{BACKEND_URL}/workflow/create-pr"

# This function encapsulates the tab's content
def show_autonomous_workflow_tab():
    st.subheader("🧠 Autonomous Workflow Orchestration")

    st.markdown("Use this panel to trigger any part of the DebugIQ agent workflow or run the full end-to-end fix pipeline.")

    # --- Upload raw issue input for triage ---
    st.markdown("### 📨 Ingest New Issue")

    uploaded_issue_file = st.file_uploader("Upload raw issue JSON (e.g. trace or monitoring event)", type=["json"])
    if uploaded_issue_file:
        try:
            raw_json = json.load(uploaded_issue_file)
            if st.button("🚀 Triage with AI"):
                with st.spinner("Triage in progress..."):
                    resp = requests.post(TRIAGE_URL, json={"raw_data": raw_json})
                    if resp.status_code == 200:
                         st.success("Triage complete!")
                         st.json(resp.json())
                    else:
                         st.error(f"Triage failed: {resp.status_code}")
                         st.error(f"Response body: {resp.text}")
        except json.JSONDecodeError:
            st.error("Invalid JSON file.")
        except requests.exceptions.RequestException as e:
            st.error(f"Error communicating with backend: {e}")


    # --- Run full workflow ---
    st.markdown("### ⚙️ Run Full Workflow")
    issue_id_full = st.text_input("Issue ID to fully auto-fix", key="workflow_full_id")
    if st.button("Run Full AI Workflow"):
        if issue_id_full:
            try:
                resp = requests.post(RUN_WORKFLOW_URL, json={"issue_id": issue_id_full})
                if resp.status_code == 200:
                     st.success(f"Workflow triggered for Issue ID: {issue_id_full}")
                     st.json(resp.json())
                else:
                     st.error(f"Failed to trigger workflow: {resp.status_code}")
                     st.error(f"Response body: {resp.text}")
            except requests.exceptions.RequestException as e:
                 st.error(f"Error communicating with backend: {e}")
        else:
            st.warning("Please enter an Issue ID.")


    # --- Modular Controls ---
    st.markdown("### 🛠️ Manual Agent Controls")

    issue_id = st.text_input("Issue ID", key="manual_issue_id")
    patch_diff = st.text_area("Paste Patch Diff for Validation", key="manual_patch_diff", height=200) # Added height for usability

    cols = st.columns(3)

    with cols[0]:
        if st.button("🔬 Diagnose"):
            if issue_id:
                try:
                    r = requests.post(DIAGNOSE_URL, json={"issue_id": issue_id})
                    if r.status_code == 200:
                         st.success(f"Diagnosis complete for Issue ID: {issue_id}")
                         st.json(r.json())
                    else:
                         st.error(f"Diagnosis failed: {r.status_code}")
                         st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                     st.error(f"Error communicating with backend: {e}")
            else:
                st.warning("Please enter an Issue ID.")


    with cols[1]:
        if st.button("✅ Validate Patch"):
            if issue_id and patch_diff:
                try:
                    r = requests.post(VALIDATE_URL, json={"issue_id": issue_id, "patch_diff_content": patch_diff})
                    if r.status_code == 200:
                        st.success(f"Validation complete for Issue ID: {issue_id}")
                        st.json(r.json())
                    else:
                        st.error(f"Validation failed: {r.status_code}")
                        st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend: {e}")
            else:
                st.warning("Please enter both Issue ID and Patch Diff.")


    with cols[2]:
        if st.button("📤 Create PR"):
            if issue_id:
                try:
                    r = requests.post(CREATE_PR_URL, json={"issue_id": issue_id})
                    if r.status_code == 200 or r.status_code == 201: # PR creation might return 201 Created
                        st.success(f"PR creation triggered for Issue ID: {issue_id}")
                        st.json(r.json())
                    else:
                        st.error(f"Create PR failed: {r.status_code}")
                        st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend: {e}")
            else:
                st.warning("Please enter an Issue ID.")

# Example of how you would use this in your main streamlit-dashboard.py:
# from frontend.screens.AutonomousWorkflowTab import show_autonomous_workflow_tab
#
# # Inside your tab definition:
# with tab6: # Assuming you add a 6th tab
#    show_autonomous_workflow_tab()
