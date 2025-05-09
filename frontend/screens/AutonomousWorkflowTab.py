# Save this code as AutonomousWorkflowTab.py at DebuIQ-frontend/.screens/AutonomousWorkflowTab.py
# Ensure __init__.py files are in DebuIQ-frontend/frontend/ and DebuIQ-frontend/.screens/

import streamlit as st
import requests
import json
# Import os if you want to use os.getenv for BACKEND_URL fallback *within* the function
import os # Keep if needed, but BACKEND_URL is passed in now

# Define the function that renders the tab content
# BACKEND_URL is now passed as an argument
def show_autonomous_workflow_tab(backend_url):
    # Define URLs *inside* the function where they are used
    # Use the passed backend_url
    TRIAGE_URL = f"{backend_url}/workflow/triage"
    RUN_WORKFLOW_URL = f"{backend_url}/workflow/run"
    DIAGNOSE_URL = f"{backend_url}/workflow/diagnose"
    VALIDATE_URL = f"{backend_url}/workflow/validate"
    CREATE_PR_URL = f"{backend_url}/workflow/create-pr"

    # --- All st commands are now inside this function ---
    st.subheader("🧠 Autonomous Workflow Orchestration")

    st.markdown("Use this panel to trigger any part of the DebugIQ agent workflow or run the full end-to-end fix pipeline.")

    # --- Upload raw issue input for triage ---
    st.markdown("### 📨 Ingest New Issue")

    uploaded_issue_file = st.file_uploader("Upload raw issue JSON (e.g. trace or monitoring event)", type=["json"], key="ingest_issue_uploader") # Added key
    if uploaded_issue_file:
        try:
            raw_json = json.load(uploaded_issue_file)
            if st.button("🚀 Triage with AI", key="triage_button"): # Added key
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
            st.error(f"Error communicating with backend for triage: {e}")


    # --- Run full workflow ---
    st.markdown("### ⚙️ Run Full Workflow")
    issue_id_full = st.text_input("Issue ID to fully auto-fix", key="workflow_full_id_input") # Added key
    if st.button("Run Full AI Workflow", key="run_full_workflow_button"): # Added key
        if issue_id_full:
            try:
                with st.spinner(f"Running full workflow for issue {issue_id_full}..."):
                    resp = requests.post(RUN_WORKFLOW_URL, json={"issue_id": issue_id_full})
                    if resp.status_code == 200:
                         st.success(f"Full workflow triggered for Issue ID: {issue_id_full}")
                         st.json(resp.json())
                    else:
                         st.error(f"Failed to trigger full workflow: {resp.status_code}")
                         st.error(f"Response body: {resp.text}")
            except requests.exceptions.RequestException as e:
                 st.error(f"Error communicating with backend for full workflow: {e}")
        else:
            st.warning("Please enter an Issue ID.")

    # --- Modular Controls ---
    st.markdown("### 🛠️ Manual Agent Controls")

    issue_id = st.text_input("Issue ID", key="manual_issue_id_input") # Added key
    patch_diff = st.text_area("Paste Patch Diff for Validation", key="manual_patch_diff_input", height=200) # Added key and height

    cols = st.columns(3)

    with cols[0]:
        if st.button("🔬 Diagnose", key="diagnose_button"): # Added key
            if issue_id:
                try:
                    with st.spinner(f"Diagnosing issue {issue_id}..."):
                        r = requests.post(DIAGNOSE_URL, json={"issue_id": issue_id})
                        if r.status_code == 200:
                             st.success(f"Diagnosis complete for Issue ID: {issue_id}")
                             st.json(r.json())
                        else:
                             st.error(f"Diagnosis failed: {r.status_code}")
                             st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                     st.error(f"Error communicating with backend for diagnose: {e}")
            else:
                st.warning("Please enter an Issue ID.")

    with cols[1]:
        if st.button("✅ Validate Patch", key="validate_patch_button"): # Added key
            if issue_id and patch_diff:
                try:
                    with st.spinner(f"Validating patch for issue {issue_id}..."):
                        r = requests.post(VALIDATE_URL, json={"issue_id": issue_id, "patch_diff_content": patch_diff})
                        if r.status_code == 200:
                            st.success(f"Validation complete for Issue ID: {issue_id}")
                            st.json(r.json())
                        else:
                            st.error(f"Validation failed: {r.status_code}")
                            st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend for validate: {e}")
            else:
                st.warning("Please enter both Issue ID and Patch Diff.")

    with cols[2]:
        if st.button("📤 Create PR", key="create_pr_button"): # Added key
            if issue_id:
                try:
                    with st.spinner(f"Creating PR for issue {issue_id}..."):
                        r = requests.post(CREATE_PR_URL, json={"issue_id": issue_id})
                        if r.status_code == 200 or r.status_code == 201: # PR creation might return 201 Created
                            st.success(f"PR creation triggered for Issue ID: {issue_id}")
                            st.json(r.json())
                        else:
                            st.error(f"Create PR failed: {r.status_code}")
                            st.error(f"Response body: {r.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend for Create PR: {e}")
            else:
                st.warning("Please enter an Issue ID.")

# The function ends here. No st commands should be outside this function.
