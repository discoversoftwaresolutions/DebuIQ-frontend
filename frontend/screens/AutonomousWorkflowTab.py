import streamlit as st
import requests
import os
import difflib
import tempfile
from streamlit_ace import st_ace
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings, WebRtcMode
import numpy as np
import av
from difflib import HtmlDiff
import streamlit.components.v1 as components
import wave # Import wave for proper WAV writing
import json # Import json for file handling

# --- Import the Autonomous Workflow Tab function ---
# IMPORTANT: This uses a relative import to a sibling directory
# Make sure AutonomousWorkflowTab.py is at DebuIQ-frontend/.screens/AutonomousWorkflowTab.py
# AND that you have empty __init__.py files in:
# - DebuIQ-frontend/frontend/__init__.py
# - DebuIQ-frontend/.screens/__init__.py
autonomous_tab_imported = False
show_autonomous_workflow_tab = None
try:
    # Changed to relative import: go up one level (..) then into screens
    from ..screens.AutonomousWorkflowTab import show_autonomous_workflow_tab
    autonomous_tab_imported = True
except ImportError as e:
    # Do NOT use st.error here, just set the flag and handle the error later
    autonomous_tab_imported = False
    show_autonomous_tab_import_error = str(e) # Store the error message
    show_autonomous_workflow_tab = None # Ensure it's None


# --- Streamlit Page Configuration ---
# set_page_config() MUST be the very first Streamlit command after imports
st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")

st.title("🧠 DebugIQ Autonomous Debugging Dashboard")

# --- Display import error *after* set_page_config ---
if not autonomous_tab_imported:
    st.error(f"Could not import the Autonomous Workflow Orchestration tab: {show_autonomous_tab_import_error}. "
             f"Make sure AutonomousWorkflowTab.py is at the correct path (DebuIQ-frontend/.screens/) "
             f"and __init__.py files are in the 'frontend' and '.screens' directories.")


# Corrected the syntax error in os.getenv by adding quotes around the default URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://debugiq-backend.onrender.com")


@st.cache_data
def fetch_config(backend_url): # Pass backend_url to cache function dependencies
    """Fetches backend configuration, error handling is done after the call."""
    try:
        r = requests.get(f"{backend_url}/api/config")
        r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        return r.json()
    except requests.exceptions.RequestException as e:
        # Return None or raise a specific exception, but avoid st.error inside
        print(f"Error fetching config: {e}") # Log to console/logs
        return None

# --- Fetch and Display Config (Moved after set_page_config) ---
config = fetch_config(BACKEND_URL) # Call the function

if config:
    st.sidebar.info("Backend Config Loaded:")
    st.sidebar.json(config) # Display full config for debugging
    # st.sidebar.info(f"🔧 Voice Provider: {config.get('voice_provider', 'N/A')}") # Specific info if needed
    # st.sidebar.info(f"🧠 Model: {config.get('model', 'N/A')}") # Specific info if needed
else:
    st.sidebar.warning("Backend config not loaded. Using default URLs. Check logs for errors.")


# Use fetched URLs, falling back to defaults constructed with BACKEND_URL
ANALYZE_URL = config.get("analyze_url", f"{BACKEND_URL}/debugiq/analyze") if config else f"{BACKEND_URL}/debugiq/analyze"
QA_URL = config.get("qa_url", f"{BACKEND_URL}/qa/") if config else f"{BACKEND_URL}/qa/"
TRANSCRIBE_URL = config.get("voice_transcribe_url", f"{BACKEND_URL}/voice/transcribe") if config else f"{BACKEND_URL}/voice/transcribe"
COMMAND_URL = config.get("voice_command_url", f"{BACKEND_URL}/voice/command") if config else f"{BACKEND_URL}/voice/command"

# --- Session State Initialization ---
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = {
        'trace': None,
        'patch': None,
        'explanation': None,
        'doc_summary': None,
        'patched_file_name': None,
        'original_patched_file_content': None,
        'source_files_content': {}
    }
if 'qa_result' not in st.session_state:
    st.session_state.qa_result = None

# === GitHub Repo Integration Sidebar ===
st.sidebar.markdown("### 📦 Load From GitHub Repo")
repo_url = st.sidebar.text_input("Public GitHub URL", placeholder="https://github.com/user/repo", key="github_repo_url_input") # Changed key


if repo_url:
    try:
        import re
        # base64 import is not used in this block, can be removed if not used elsewhere
        # import base64

        match = re.match(r"https://github.com/([^/]+)/([^/]+)", repo_url.strip())
        if match:
            owner, repo = match.groups()
            # Use st.session_state for caching GitHub data instead of @st.cache_data if interactive state matters
            if "github_branches" not in st.session_state or st.session_state.get("current_github_repo_url") != repo_url:
                 st.session_state.current_github_repo_url = repo_url # Store the *successfully loaded* URL
                 branches_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/branches")
                 if branches_res.status_code == 200:
                     st.session_state.github_branches = [b["name"] for b in branches_res.json()]
                     # Reset path and selected branch when repo changes
                     st.session_state.github_path_stack = [""]
                     if st.session_state.github_branches:
                         # Set default branch, handle case with no branches
                         st.session_state.github_selected_branch = st.session_state.github_branches[0]
                     else:
                         st.session_state.github_selected_branch = None
                         st.sidebar.warning("No branches found for this repository.")
                     st.sidebar.success(f"Repository '{owner}/{repo}' loaded.")

                 else:
                     st.sidebar.error(f"❌ Invalid repo or cannot fetch branches ({branches_res.status_code}). Please check URL.")
                     st.session_state.github_branches = []
                     st.session_state.github_selected_branch = None
                     st.session_state.github_path_stack = [""]
                     st.session_state.current_github_repo_url = None # Clear successful URL if fetch fails

            branches = st.session_state.get("github_branches", [])
            selected_branch = st.sidebar.selectbox("Branch", branches, key="github_branch_select")

            if selected_branch:
                # Directory navigator
                if "github_path_stack" not in st.session_state:
                     st.session_state.github_path_stack = [""]

                path_stack = st.session_state.github_path_stack
                current_path = "/".join([p for p in path_stack if p])

                # Fetch content for the current path and branch
                content_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{current_path}?ref={selected_branch}"
                # Cache content based on URL and path/branch
                @st.cache_data(ttl=600) # Cache content for 10 minutes
                def fetch_github_content(url, current_path_key, selected_branch_key): # Include keys for caching dependency
                    try:
                        content_res = requests.get(url)
                        content_res.raise_for_status()
                        return content_res.json()
                    except requests.exceptions.RequestException as e:
                         st.sidebar.warning(f"Cannot fetch directory content from {url} ({e}).")
                         return None

                # Pass path and branch as keys for caching
                entries = fetch_github_content(content_url, current_path, selected_branch)

                if entries is not None:
                    dirs = sorted([e["name"] for e in entries if e["type"] == "dir"]) # Sort for better navigation
                    files = sorted([e["name"] for e in entries if e["type"] == "file"]) # Sort files

                    # Navigation buttons for directories
                    st.sidebar.markdown("##### 📁 Navigate")
                    if current_path: # Only show ".." if not in the root
                         # Using st.form allows multiple buttons without immediate rerun until form submit
                         # Or manage state carefully with st.button callbacks
                         if st.sidebar.button("..", key="github_up_dir"):
                             st.session_state.github_path_stack.pop()
                             st.rerun() # Use st.rerun() for newer Streamlit versions

                    # Create buttons for subdirectories
                    for d in dirs:
                        if st.sidebar.button(d, key=f"github_dir_{d}"):
                            st.session_state.github_path_stack.append(d)
                            st.rerun() # Use st.rerun()

                    st.sidebar.markdown("##### 📄 Files")
                    # Create buttons for files
                    for f in files:
                        if st.sidebar.button(f, key=f"github_file_{f}"):
                            file_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{selected_branch}/{current_path}/{f}".rstrip("/")
                            try:
                                file_content_res = requests.get(file_url)
                                file_content_res.raise_for_status()
                                file_content = file_content_res.text
                                st.sidebar.success(f"Loaded: {f}")
                                # Set the trace or source file based on extension
                                if f.endswith(".txt"):
                                    st.session_state.analysis_results["trace"] = file_content
                                    st.session_state.analysis_results["source_files_content"].pop(f, None) # Remove if it was listed as source
                                elif f.endswith((".py", ".js", ".java", ".c", ".cpp", ".cs", ".go", ".rb", ".php", ".html", ".css", ".txt", ".md")): # Add other relevant source extensions
                                    # Store with full path from repo root for clarity
                                    full_file_path = os.path.join(current_path, f).replace("\\", "/") if current_path else f # Use / for paths
                                    st.session_state.analysis_results["source_files_content"][full_file_path] = file_content
                                    # Decide if loading a source file should clear the trace - currently it does if the source file is txt
                                    # if f.endswith(".txt"): # This condition was inside the elif block, likely a copy-paste error
                                    #    st.session_state.analysis_results["trace"] = None # Clear trace if a non-trace file is loaded? Depends on logic
                                else:
                                     st.sidebar.warning(f"Ignoring file '{f}' - unsupported extension for analysis/source files.")

                            except requests.exceptions.RequestException as e:
                                st.sidebar.error(f"Failed to load file {f} from {file_url}: {e}")

                else: # If entries is None (fetch_github_content returned None)
                     st.sidebar.warning("Could not list files in this directory.")


            elif branches: # Case where branches were fetched but none are selected (e.g., empty repo or fetch issue)
                 st.sidebar.warning("No branches available or selected.")

        else:
            st.sidebar.warning("Please enter a valid GitHub repo URL.")

    except Exception as e:
        # Catch any other unexpected errors during GitHub interaction
        st.sidebar.error(f"⚠️ An unexpected error occurred during GitHub interaction: {e}")


# File uploader (remains as alternative input)
st.markdown("---") # Separator
st.markdown("### ⬆️ Upload Files Manually")
uploaded_files = st.file_uploader("📄 Upload traceback (.txt) + source files", type=["txt", "py"], accept_multiple_files=True, key="manual_file_uploader") # Added key

if uploaded_files:
    trace_content_upload = None
    source_files_content_upload = {}
    for file in uploaded_files:
        content = file.getvalue().decode("utf-8")
        if file.name.endswith(".txt"):
            trace_content_upload = content
        else:
            source_files_content_upload[file.name] = content # Store with original filename

    # Decide whether to use uploaded files or GitHub files - uploaded takes precedence if new files are uploaded
    # Only update session state if files were actually uploaded in this run
    if trace_content_upload is not None or source_files_content_upload:
         if trace_content_upload is not None:
             st.session_state.analysis_results['trace'] = trace_content_upload
             st.session_state.analysis_results['source_files_content'] = {} # Clear source files if new trace is uploaded
             # Clear GitHub state as manual upload overrides it
             st.session_state.github_repo_url_input = ""
             st.session_state.current_github_repo_url = None
             if "github_branches" in st.session_state: del st.session_state.github_branches
             if "github_selected_branch" in st.session_state: del st.session_state.github_selected_branch
             if "github_path_stack" in st.session_state: del st.session_state.github_path_stack

             st.success("✅ Traceback uploaded and loaded.")

         if source_files_content_upload:
             # If trace wasn't uploaded, but source files were, potentially clear existing source files
             # This logic depends on whether you want uploads to *add* to or *replace* existing source files
             # Current: update/merge source files, clear trace if a trace was just uploaded
             # Alternative: clear all existing source files before adding new ones
             # st.session_state.analysis_results['source_files_content'] = {} # Uncomment to replace existing source files

             st.session_state.analysis_results['source_files_content'].update(source_files_content_upload) # Use update to merge
             # st.session_state.analysis_results['trace'] = None # Uncomment to clear trace if source files are uploaded

             # Clear GitHub state as manual upload overrides it
             st.session_state.github_repo_url_input = ""
             st.session_state.current_github_repo_url = None
             if "github_branches" in st.session_state: del st.session_state.github_branches
             if "github_selected_branch" in st.session_state: del st.session_state.github_selected_branch
             if "github_path_stack" in st.session_state: del st.session_state.github_path_stack

             st.success(f"✅ Source files uploaded and loaded: {list(source_files_content_upload.keys())}")


# Define Tabs - Changed the order of tab 5 and 6
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔧 Patch",
    "✅ QA",
    "📘 Docs",
    "📥 Issue Inbox",
    "🤖 Workflow Orchestration", # Moved to 5th position
    "🔁 Workflow Status"      # Moved to 6th position
])

with tab1:
    st.subheader("Traceback Analysis + Patch")
    if st.button("🧠 Run DebugIQ Analysis", key="run_analysis_button"): # Added key
        if st.session_state.analysis_results.get('trace') is None and not st.session_state.analysis_results.get('source_files_content'): # Use .get()
            st.warning("Please upload a traceback or source files from the sidebar or below.")
        else:
            with st.spinner("Analyzing with GPT-4o..."):
                try:
                    res = requests.post(ANALYZE_URL, json={
                        "trace": st.session_state.analysis_results.get('trace'), # Use .get()
                        "language": "python", # Assuming python, adjust if needed
                        "config": {}, # Pass relevant config if needed
                        "source_files": st.session_state.analysis_results.get('source_files_content', {}) # Use .get()
                    })

                    if res.status_code == 200:
                        result = res.json()
                        st.session_state.analysis_results.update({
                            'patch': result.get("patch"),
                            'explanation': result.get("explanation"),
                            'doc_summary': result.get("doc_summary"),
                            'patched_file_name': result.get("patched_file_name"),
                            'original_patched_file_content': result.get("original_patched_file_content")
                        })
                        st.success("✅ Analysis complete. Patch generated.")
                    else:
                        st.error(f"Analysis failed: {res.status_code}")
                        st.error(f"Response body: {res.text}")
                        st.session_state.analysis_results.update({ # Clear results on failure
                            'patch': None, 'explanation': None, 'doc_summary': None,
                            'patched_file_name': None, 'original_patched_file_content': None
                        })
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend: {e}")
                    st.session_state.analysis_results.update({ # Clear results on failure
                         'patch': None, 'explanation': None, 'doc_summary': None,
                         'patched_file_name': None, 'original_patched_file_content': None
                    })


    if st.session_state.analysis_results.get('patch'): # Check if patch exists using .get()
        st.markdown("### 🔍 Patch Diff")
        original = st.session_state.analysis_results.get('original_patched_file_content', '')
        patched = st.session_state.analysis_results.get('patch', '')

        if original and patched and original != patched: # Ensure both exist and are different before showing diff
             try:
                 html_diff = HtmlDiff().make_table(
                     original.splitlines(keepends=True), patched.splitlines(keepends=True), # keepends=True for accurate diff
                     "Original", "Patched", context=True, numlines=3
                 )
                 components.html(html_diff, height=400, scrolling=True)
             except Exception as e:
                 st.error(f"Could not generate diff: {e}")
                 st.text_area("Original Content", value=original, height=200, key="orig_content_display", disabled=True)
                 st.text_area("Patched Content", value=patched, height=200, key="patch_content_display", disabled=True)

        elif patched:
             st.text_area("Generated Patch Content", value=patched, height=300, key="patch_only_display", disabled=True, label="Generated Patch Content (No Diff Available)") # Use disabled if no diff
        elif original:
             st.info("Original content loaded, but no patch has been generated yet.")
        else:
             st.info("No patch or original content available for diff.")


        st.markdown("### ✏️ Edit Patch")
        # Use the generated patch as the default value, allow editing
        # Get default value safely
        default_patch_value = st.session_state.analysis_results.get('patch', '')
        edited_patch = st_ace(
            value=default_patch_value,
            language="python", # Assuming python
            theme="monokai",
            height=300,
            key="patch_editor"
        )
        # Update the session state ONLY if the user has interacted and changed it
        # Check if the editor content is different from the *current* state value
        if edited_patch != st.session_state.analysis_results.get('patch', ''):
             st.session_state.analysis_results['patch'] = edited_patch
             # st.experimental_rerun() # May need rerun if editing affects other parts of the app immediately


        st.markdown("### 💬 Explanation")
        st.text_area("Patch Explanation", value=st.session_state.analysis_results.get('explanation', 'No explanation available.'), height=150, disabled=True, key="explanation_display") # Disable editing explanation?

with tab2:
    st.subheader("Run Quality Assurance on Patch")
    if st.button("🛡️ Run QA on Patch", key="run_qa_button"): # Added key
        if st.session_state.analysis_results.get('patch') is None:
            st.warning("Please run analysis and generate a patch first.")
        elif st.session_state.analysis_results.get('patched_file_name') is None:
            st.warning("Analysis results are missing the patched file name. Rerun analysis.")
        else:
            with st.spinner("Running QA..."):
                try:
                    qa_res = requests.post(QA_URL, json={
                        "trace": st.session_state.analysis_results.get('trace'),
                        "patch": st.session_state.analysis_results['patch'], # Use potentially edited patch
                        "language": "python", # Assuming python
                        "source_files": st.session_state.analysis_results.get('source_files_content', {}),
                        "patched_file_name": st.session_state.analysis_results['patched_file_name']
                    })
                    if qa_res.status_code == 200:
                         qa_data = qa_res.json()
                         st.session_state.qa_result = qa_data
                         st.success("✅ QA complete")
                    else:
                         st.error(f"QA failed: {qa_res.status_code}")
                         st.error(f"Response body: {qa_res.text}")
                         st.session_state.qa_result = None # Clear previous result on failure
                except requests.exceptions.RequestException as e:
                     st.error(f"Error communicating with backend: {e}")
                     st.session_state.qa_result = None # Clear previous result on failure


    if st.session_state.get('qa_result'): # Check if qa_result exists
        st.markdown("### LLM Review")
        st.markdown(st.session_state.qa_result.get("llm_qa_result", "No LLM feedback."))
        st.markdown("### Static Analysis")
        static_analysis_result = st.session_state.qa_result.get("static_analysis_result", {})
        if static_analysis_result:
            st.json(static_analysis_result)
        else:
            st.info("No static analysis results available.")


with tab3:
    st.subheader("📘 Auto-Generated Documentation")
    doc_summary = st.session_state.analysis_results.get("doc_summary", "No documentation available.")
    st.markdown(doc_summary)


with tab4:
    st.subheader("📥 Issue Inbox")
    # Using a button in the main area to refresh is clearer
    if st.button("🔄 Refresh Inbox", key="refresh_inbox_button"):
         # Clearing cache_data *might* be too broad. Better to manage state in session_state.
         # st.cache_data.clear() # Consider removing if only session_state is used for inbox_data
         st.session_state.inbox_data = None # Clear session state cache
         st.rerun() # Rerun to show updated data


    inbox_url = f"{BACKEND_URL}/issues/inbox"
    # @st.cache_data(ttl=30) # Cache inbox data for 30 seconds - Can use alongside session_state
    # def fetch_inbox_cached(url): # Define a separate cached function
    #    try:
    #        r = requests.get(url)
    #        r.raise_for_status()
    #        return r.json()
    #    except requests.exceptions.RequestException as e:
    #        print(f"Error fetching inbox: {e}")
    #        return None

    # Fetch data only if not in session_state cache or if it's explicitly cleared
    if "inbox_data" not in st.session_state or st.session_state.inbox_data is None:
        try:
            with st.spinner("Loading inbox..."):
                # Use requests directly or call the cached function here
                r = requests.get(inbox_url)
                r.raise_for_status()
                st.session_state.inbox_data = r.json()
        except requests.exceptions.RequestException as e:
             st.error(f"Failed to load inbox: {e}")
             st.session_state.inbox_data = None # Ensure it's None on failure


    inbox = st.session_state.inbox_data

    if inbox and inbox.get("issues"):
        for issue in inbox.get("issues", []):
            issue_id = issue.get('id', 'N/A')
            issue_classification = issue.get('classification', 'N/A')
            issue_status = issue.get('status', 'N/A')
            # Use unique key for expander and button
            with st.expander(f"Issue {issue_id} - {issue_classification} [{issue_status}]", expanded=False):
                st.json(issue)
                # Use unique key for button
                if st.button(f"▶️ Trigger Workflow for {issue_id}", key=f"trigger_workflow_button_{issue_id}"):
                     workflow_run_url = f"{BACKEND_URL}/workflow/run"
                     try:
                         # Use a temporary spinner/status message
                         with st.spinner(f"Triggering workflow for {issue_id}..."):
                             r = requests.post(workflow_run_url, json={"issue_id": issue_id})
                             r.raise_for_status()
                             st.success(f"Workflow triggered for {issue_id}!")
                             # Optionally refresh inbox after triggering
                             st.session_state.inbox_data = None # Clear cache
                             st.rerun() # Rerun to show updated status quickly
                     except requests.exceptions.RequestException as e:
                          st.error(f"Failed to trigger workflow for {issue_id}: {e}")


    elif inbox is not None: # inbox is not None but has no issues key or issues list
        st.info("No issues in the inbox.")
    # else: inbox is None meaning fetch failed entirely, error message already shown


# === The Autonomous Workflow Orchestration Tab (Now Tab 5) ===
with tab5: # Changed from tab6 to tab5
    # Call the function imported from AutonomousWorkflowTab.py
    if autonomous_tab_imported: # Only call if the import was successful
        show_autonomous_workflow_tab()
    # The error message for import failure is displayed at the top


# === Workflow Status Tab (Now Tab 6) ===
with tab6: # Changed from tab5 to tab6
    st.subheader("🔁 Live Workflow Timeline")
    if st.button("🔄 Refresh Status", key="refresh_status_button"): # Added key
        st.session_state.workflow_status = None # Clear session state cache
        # st.cache_data.clear() # Consider removing

    status_url = f"{BACKEND_URL}/workflow/status"
    # @st.cache_data(ttl=5) # Cache status data for 5 seconds - Can use alongside session_state
    # def fetch_status_cached(url): # Define a separate cached function
    #     try:
    #         r = requests.get(url)
    #         r.raise_for_status()
    #         return r.json()
    #     except requests.exceptions.RequestException as e:
    #         print(f"Error fetching status: {e}")
    #         return None

    # Fetch data only if not in session_state cache or if it's explicitly cleared
    if "workflow_status" not in st.session_state or st.session_state.workflow_status is None:
        try:
            with st.spinner("Loading workflow status..."):
                # Use requests directly or call the cached function here
                r = requests.get(status_url)
                r.raise_for_status()
                st.session_state.workflow_status = r.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to load workflow status: {e}")
            st.session_state.workflow_status = None # Ensure None on failure

    workflow_status = st.session_state.workflow_status

    if workflow_status:
        st.json(workflow_status)
    elif workflow_status is not None: # Status was fetched but is empty/not valid JSON structure expected
        st.info("Workflow status data is empty or in an unexpected format.")
    # else: workflow_status is None meaning fetch failed, error message already shown


# === Voice Agent Section ===
st.markdown("---") # Separator
st.markdown("## 🎙️ DebugIQ Voice Agent")

# The webrtc_streamer component handles its own state and UI (Start/Stop button)
# Use a key based on BACKEND_URL so the component resets if the backend changes
ctx = webrtc_streamer(
    key=f"voice_agent_stream_{BACKEND_URL}", # Use a unique key, dependent on URL
    mode=WebRtcMode.SENDONLY, # Send audio from browser to server
    client_settings=ClientSettings(
        media_stream_constraints={"audio": True, "video": False},
        # Use a list for iceServers, even if only one
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    ),
    # audio_receiver_size parameter is deprecated
)

# Process audio frames if the connection is active and audio_receiver is available
# Use st.session_state to buffer frames if necessary across reruns
if "audio_buffer" not in st.session_state:
     st.session_state.audio_buffer = b""
if "audio_frame_count" not in st.session_state:
     st.session_state.audio_frame_count = 0
if "audio_sample_rate" not in st.session_state:
     st.session_state.audio_sample_rate = 16000 # Default common sample rate
if "audio_sample_width" not in st.session_state:
     st.session_state.audio_sample_width = 2 # Default 16-bit audio (2 bytes)
if "audio_num_channels" not in st.session_state:
     st.session_state.audio_num_channels = 1 # Default mono

if ctx and ctx.audio_receiver:
    try:
        # Get frames with a small timeout
        audio_frames = ctx.audio_receiver.get_frames(timeout=0.1)

        if audio_frames:
            # Try to infer audio parameters from the first frame if not set
            # Note: Consistency of format across frames is assumed
            if st.session_state.audio_sample_rate == 16000 and audio_frames[0].format.rate:
                st.session_state.audio_sample_rate = audio_frames[0].format.rate
            if st.session_state.audio_sample_width == 2 and audio_frames[0].format.bytes:
                 st.session_state.audio_sample_width = audio_frames[0].format.bytes
            if st.session_state.audio_num_channels == 1 and audio_frames[0].format.channels:
                 st.session_state.audio_num_channels = audio_frames[0].format.channels


            # Append audio data to buffer
            for frame in audio_frames:
                 # Ensure frame is in the expected format (e.g., int16)
                 # Assuming frame is initially float or int, convert to int16 bytes
                 # This might require more sophisticated handling based on actual frame format
                 if frame.format.name == 's16': # Signed 16-bit integers
                      audio_data = frame.to_ndarray().tobytes()
                 elif frame.format.name == 'flt32': # 32-bit floats
                      # Convert float32 to int16
                      audio_data = (frame.to_ndarray() * (2**15)).astype(np.int16).tobytes()
                 else:
                      st.warning(f"Unsupported audio format received: {frame.format.name}")
                      continue # Skip frame if format is unknown

                 st.session_state.audio_buffer += audio_data
                 st.session_state.audio_frame_count += frame.samples # Sum up samples

            st.sidebar.text(f"Buffered: {st.session_state.audio_frame_count} samples")

            # --- Process buffer periodically (Example) ---
            # Define a threshold for processing (e.g., 1 second of audio)
            # Convert seconds to samples based on the determined sample rate
            processing_threshold_seconds = 1
            processing_threshold_samples = processing_threshold_seconds * st.session_state.audio_sample_rate


            if st.session_state.audio_frame_count >= processing_threshold_samples and st.session_state.audio_buffer:
                st.info(f"Processing ~{st.session_state.audio_frame_count/st.session_state.audio_sample_rate:.2f} seconds of audio...")
                # Write buffered data to a temp WAV and send
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav_file:
                    wav_writer = wave.open(tmp_wav_file.name, 'wb')
                    # Use parameters determined from frames or defaults
                    wav_writer.setnchannels(st.session_state.audio_num_channels)
                    wav_writer.setsampwidth(st.session_state.audio_sample_width)
                    wav_writer.setframerate(st.session_state.audio_sample_rate)
                    wav_writer.writeframes(st.session_state.audio_buffer)
                    wav_writer.close()

                # Send the temporary file for transcription
                files = {"file": open(tmp_wav_file.name, "rb")}
                try:
                    transcribe_res = requests.post(TRANSCRIBE_URL, files=files)
                    transcribe_res.raise_for_status()
                    transcript_data = transcribe_res.json()
                    transcript = transcript_data.get("transcript")
                    if transcript:
                        st.success(f"🗣️ Transcribed: {transcript}")
                        # Send transcript as command
                        command_res = requests.post(COMMAND_URL, json={"text_command": transcript})
                        command_res.raise_for_status()
                        command_data = command_res.json()
                        st.info(f"🤖 GPT-4o: {command_data.get('spoken_text', 'No response.')}")
                    else:
                         st.info("Transcription returned empty.")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error during transcription or command: {e}")
                except Exception as e:
                    st.error(f"Error processing transcription or command response: {e}")
                finally:
                    # Clean up the temporary file
                    os.remove(tmp_wav_file.name)
                    # Clear the buffer AFTER processing
                    st.session_state.audio_buffer = b""
                    st.session_state.audio_frame_count = 0


    except av.TimeoutError:
        # This is expected if no frames are available within the timeout
        pass
    except Exception as e:
         st.error(f"An unexpected error occurred in audio receiver: {e}")
