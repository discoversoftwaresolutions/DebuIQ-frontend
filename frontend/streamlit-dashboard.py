# Save this code as streamlit-dashboard.py in your project's source code.
# This is your main Streamlit application file.

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

# Import the Autonomous Workflow Tab function
# Make sure frontend/screens/AutonomousWorkflowTab.py exists in your repo
try:
    from frontend.screens.AutonomousWorkflowTab import show_autonomous_workflow_tab
except ImportError:
    st.error("Could not import the Autonomous Workflow Tab. Make sure frontend/screens/AutonomousWorkflowTab.py exists.")
    show_autonomous_workflow_tab = None # Define a placeholder if import fails


st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Autonomous Debugging Dashboard")

# Corrected the syntax error in os.getenv by adding quotes around the default URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://debugiq-backend.onrender.com")


@st.cache_data
def fetch_config(backend_url): # Pass backend_url to cache function dependencies
    try:
        r = requests.get(f"{backend_url}/api/config")
        if r.status_code == 200:
            return r.json()
        else:
             st.warning(f"Backend config not found: {r.status_code}")
    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ Could not load backend config: {e}")
    return {}

config = fetch_config(BACKEND_URL) # Pass the URL when calling
if config:
    st.sidebar.info(f"🔧 Voice Provider: {config.get('voice_provider', 'N/A')}")
    st.sidebar.info(f"🧠 Model: {config.get('model', 'N/A')}")
else:
    st.sidebar.warning("Backend config not loaded. Using default URLs.")


# Use fetched URLs, falling back to defaults constructed with BACKEND_URL
ANALYZE_URL = config.get("analyze_url", f"{BACKEND_URL}/debugiq/analyze")
QA_URL = config.get("qa_url", f"{BACKEND_URL}/qa/")
TRANSCRIBE_URL = config.get("voice_transcribe_url", f"{BACKEND_URL}/voice/transcribe")
COMMAND_URL = config.get("voice_command_url", f"{BACKEND_URL}/voice/command")

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
repo_url = st.sidebar.text_input("Public GitHub URL", placeholder="https://github.com/user/repo", key="github_repo_url")

if repo_url:
    try:
        import re
        import base64

        match = re.match(r"https://github.com/([^/]+)/([^/]+)", repo_url.strip())
        if match:
            owner, repo = match.groups()
            # Use st.session_state for caching GitHub data instead of @st.cache_data if interactive state matters
            if "github_branches" not in st.session_state or st.session_state.github_repo_url != repo_url:
                 st.session_state.github_repo_url = repo_url
                 branches_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/branches")
                 if branches_res.status_code == 200:
                     st.session_state.github_branches = [b["name"] for b in branches_res.json()]
                     # Reset path and selected branch when repo changes
                     st.session_state.github_path_stack = [""]
                     if st.session_state.github_branches:
                         st.session_state.github_selected_branch = st.session_state.github_branches[0]
                     else:
                         st.session_state.github_selected_branch = None
                 else:
                     st.sidebar.error(f"❌ Invalid repo or cannot fetch branches ({branches_res.status_code}).")
                     st.session_state.github_branches = []
                     st.session_state.github_selected_branch = None
                     st.session_state.github_path_stack = [""]

            branches = st.session_state.github_branches
            selected_branch = st.sidebar.selectbox("Branch", branches, key="github_branch_select")

            if selected_branch:
                # Directory navigator
                if "github_path_stack" not in st.session_state:
                     st.session_state.github_path_stack = [""]

                path_stack = st.session_state.github_path_stack
                current_path = "/".join([p for p in path_stack if p])

                # Fetch content for the current path and branch
                content_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{current_path}?ref={selected_branch}"
                @st.cache_data(ttl=600) # Cache content for 10 minutes
                def fetch_github_content(url):
                    try:
                        content_res = requests.get(url)
                        if content_res.status_code == 200:
                            return content_res.json()
                        else:
                             st.sidebar.warning(f"Cannot fetch directory content ({content_res.status_code}).")
                             return None
                    except requests.exceptions.RequestException as e:
                         st.sidebar.error(f"Error fetching directory content: {e}")
                         return None

                entries = fetch_github_content(content_url)

                if entries is not None:
                    dirs = sorted([e["name"] for e in entries if e["type"] == "dir"]) # Sort for better navigation
                    files = sorted([e["name"] for e in entries if e["type"] == "file"]) # Sort files

                    # Navigation buttons for directories
                    st.sidebar.markdown("##### 📁 Navigate")
                    if current_path: # Only show ".." if not in the root
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
                                if file_content_res.status_code == 200:
                                    file_content = file_content_res.text
                                    st.sidebar.success(f"Loaded: {f}")
                                    # Set the trace or source file based on extension
                                    if f.endswith(".txt"):
                                        st.session_state.analysis_results["trace"] = file_content
                                    else:
                                        # Store with full path from repo root for clarity
                                        full_file_path = os.path.join(current_path, f) if current_path else f
                                        st.session_state.analysis_results["source_files_content"][full_file_path] = file_content
                                else:
                                     st.sidebar.error(f"Failed to load file {f} ({file_content_res.status_code}).")
                            except requests.exceptions.RequestException as e:
                                st.sidebar.error(f"Error loading file {f}: {e}")

                # Display currently loaded files/trace
                st.sidebar.markdown("---")
                st.sidebar.markdown("#### Currently Loaded")
                if st.session_state.analysis_results['trace']:
                    st.sidebar.text("Trace Loaded")
                if st.session_state.analysis_results['source_files_content']:
                    st.sidebar.text(f"Source Files Loaded: {len(st.session_state.analysis_results['source_files_content'])}")
                    # Optional: display file names
                    # for fname in st.session_state.analysis_results['source_files_content']:
                    #     st.sidebar.text(f"- {fname}")

            elif branches: # Case where branches were fetched but none are selected (shouldn't happen with selectbox usually)
                 st.sidebar.warning("Please select a branch.")


        else:
            st.sidebar.warning("Please enter a valid GitHub repo URL.")

    except Exception as e:
        # Catch any other unexpected errors during GitHub interaction
        st.sidebar.error(f"⚠️ An error occurred during GitHub interaction: {e}")


# File uploader (remains as alternative input)
st.markdown("---") # Separator
st.markdown("### ⬆️ Upload Files Manually")
uploaded_files = st.file_uploader("📄 Upload traceback (.txt) + source files", type=["txt", "py"], accept_multiple_files=True)

if uploaded_files:
    trace_content_upload, source_files_content_upload = None, {}
    for file in uploaded_files:
        content = file.getvalue().decode("utf-8")
        if file.name.endswith(".txt"):
            trace_content_upload = content
        else:
            source_files_content_upload[file.name] = content # Store with original filename

    # Decide whether to use uploaded files or GitHub files - uploaded takes precedence if new files are uploaded
    if trace_content_upload is not None or source_files_content_upload:
         if trace_content_upload is not None:
             st.session_state.analysis_results['trace'] = trace_content_upload
         if source_files_content_upload:
             st.session_state.analysis_results['source_files_content'].update(source_files_content_upload) # Use update to merge
         st.success("✅ Files uploaded and loaded.")


# Define Tabs - Adding the Autonomous Workflow Tab as the 6th tab
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔧 Patch",
    "✅ QA",
    "📘 Docs",
    "📥 Issue Inbox",
    "🔁 Workflow Status",
    "🤖 Workflow Orchestration" # The new tab
])

with tab1:
    st.subheader("Traceback Analysis + Patch")
    if st.button("🧠 Run DebugIQ Analysis"):
        if st.session_state.analysis_results['trace'] is None and not st.session_state.analysis_results['source_files_content']:
            st.warning("Please upload a traceback or source files first.")
        else:
            with st.spinner("Analyzing with GPT-4o..."):
                try:
                    res = requests.post(ANALYZE_URL, json={
                        "trace": st.session_state.analysis_results['trace'],
                        "language": "python", # Assuming python, adjust if needed
                        "config": {}, # Pass relevant config if needed
                        "source_files": st.session_state.analysis_results['source_files_content']
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
                except requests.exceptions.RequestException as e:
                    st.error(f"Error communicating with backend: {e}")


    if st.session_state.analysis_results['patch']:
        st.markdown("### 🔍 Patch Diff")
        original = st.session_state.analysis_results.get('original_patched_file_content', '')
        patched = st.session_state.analysis_results.get('patch', '')

        if original and patched: # Ensure both exist before showing diff
             html_diff = HtmlDiff().make_table(
                 original.splitlines(), patched.splitlines(),
                 "Original", "Patched", context=True, numlines=3
             )
             components.html(html_diff, height=400, scrolling=True)
        elif patched:
             st.text_area("Generated Patch Content", value=patched, height=300)
        else:
             st.info("No patch generated or original content available for diff.")


        st.markdown("### ✏️ Edit Patch")
        # Use the generated patch as the default value, allow editing
        edited_patch = st_ace(
            value=st.session_state.analysis_results.get('patch', ''),
            language="python", # Assuming python
            theme="monokai",
            height=300,
            key="patch_editor" # Use a unique key
        )
        # Update the session state if the user edits
        if edited_patch != st.session_state.analysis_results.get('patch', ''):
            st.session_state.analysis_results['patch'] = edited_patch


        st.markdown("### 💬 Explanation")
        st.text_area("Patch Explanation", value=st.session_state.analysis_results.get('explanation', 'No explanation available.'), height=150)

with tab2:
    st.subheader("Run Quality Assurance on Patch")
    if st.button("🛡️ Run QA on Patch"):
        if st.session_state.analysis_results.get('patch') is None:
            st.warning("Please run analysis and generate a patch first.")
        elif st.session_state.analysis_results.get('patched_file_name') is None:
            st.warning("Analysis results are missing the patched file name.")
        else:
            with st.spinner("Running QA..."):
                try:
                    qa_res = requests.post(QA_URL, json={
                        "trace": st.session_state.analysis_results.get('trace'),
                        "patch": st.session_state.analysis_results['patch'],
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
                except requests.exceptions.RequestException as e:
                     st.error(f"Error communicating with backend: {e}")


    if st.session_state.qa_result:
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
    st.subheader("📥 Autonomous Issue Inbox")
    if st.button("🔄 Refresh Inbox", key="refresh_inbox"):
         st.session_state.inbox_data = None # Clear cache to force refetch

    inbox_url = f"{BACKEND_URL}/issues/inbox"
    @st.cache_data(ttl=30) # Cache inbox data for 30 seconds
    def fetch_inbox(url):
        try:
            r = requests.get(url)
            if r.status_code == 200:
                 return r.json()
            else:
                 st.error(f"Failed to fetch inbox: {r.status_code}")
                 st.error(f"Response body: {r.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to load inbox: {e}")
        return None

    # Fetch data only if not in session_state cache
    if "inbox_data" not in st.session_state or st.session_state.inbox_data is None:
        st.session_state.inbox_data = fetch_inbox(inbox_url)

    inbox = st.session_state.inbox_data

    if inbox and inbox.get("issues"):
        for issue in inbox.get("issues", []):
            issue_id = issue.get('id', 'N/A')
            issue_classification = issue.get('classification', 'N/A')
            issue_status = issue.get('status', 'N/A')
            with st.expander(f"Issue {issue_id} - {issue_classification} [{issue_status}]"):
                st.json(issue)
                # Use unique key for button
                if st.button(f"▶️ Trigger Workflow for {issue_id}", key=f"trigger_workflow_{issue_id}"):
                     workflow_run_url = f"{BACKEND_URL}/workflow/run"
                     try:
                         r = requests.post(workflow_run_url, json={"issue_id": issue_id})
                         if r.status_code == 200 or r.status_code == 201:
                              st.success(f"Triggered workflow for {issue_id}: {r.status_code}")
                              # Optionally refresh inbox after triggering
                              st.session_state.inbox_data = None # Clear cache
                              st.rerun() # Rerun to show updated status quickly
                         else:
                              st.error(f"Failed to trigger workflow for {issue_id}: {r.status_code}")
                              st.error(f"Response body: {r.text}")
                     except requests.exceptions.RequestException as e:
                          st.error(f"Error triggering workflow for {issue_id}: {e}")

    elif inbox is not None: # inbox is not None but has no issues key or issues list
        st.info("No issues in the inbox.")


with tab5:
    st.subheader("🔁 Live Workflow Timeline")
    if st.button("🔄 Refresh Status", key="refresh_status"):
        st.session_state.workflow_status = None # Clear cache to force refetch

    status_url = f"{BACKEND_URL}/workflow/status"
    @st.cache_data(ttl=5) # Cache status data for 5 seconds as it's live
    def fetch_status(url):
        try:
            r = requests.get(url)
            if r.status_code == 200:
                return r.json()
            else:
                st.error(f"Failed to fetch workflow status: {r.status_code}")
                st.error(f"Response body: {r.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to load workflow status: {e}")
        return None

    # Fetch data only if not in session_state cache
    if "workflow_status" not in st.session_state or st.session_state.workflow_status is None:
         st.session_state.workflow_status = fetch_status(status_url)

    workflow_status = st.session_state.workflow_status

    if workflow_status:
        st.json(workflow_status)
    elif workflow_status is not None: # Status was fetched but is empty/not valid JSON structure expected
        st.info("Workflow status data is empty or in an unexpected format.")


# === The NEW Autonomous Workflow Orchestration Tab (Tab 6) ===
with tab6:
    # Call the function imported from AutonomousWorkflowTab.py
    if show_autonomous_workflow_tab is not None: # Only show if the import was successful
        show_autonomous_workflow_tab()


# === Voice Agent Section ===
st.markdown("---") # Separator
st.markdown("## 🎙️ DebugIQ Voice Agent")

# Use st.session_state to persist ctx if needed across reruns, though webrtc_streamer
# often handles this internally based on the key.
if "webrtc_ctx" not in st.session_state:
    st.session_state.webrtc_ctx = None

# Add a button to start/stop explicitly if needed, or rely on webrtc_streamer UI
# if st.button("Start/Stop Voice Agent"):
#     # webrtc_streamer state can be controlled via its return value and external state
#     pass # Logic here would be more complex

# The webrtc_streamer component handles its own state and UI (Start/Stop button)
ctx = webrtc_streamer(
    key="voice_agent_stream", # Use a unique key
    mode=WebRtcMode.SENDONLY, # Send audio from browser to server
    client_settings=ClientSettings(
        media_stream_constraints={"audio": True, "video": False},
        # Use a list for iceServers, even if only one
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    ),
    # audio_receiver_size=256 # This parameter is deprecated in recent versions
)

# Process audio frames if the connection is active and audio_receiver is available
if ctx and ctx.audio_receiver:
    # Non-blocking way to get frames: poll frames periodically
    # This needs to be efficient to avoid blocking the Streamlit app
    try:
        audio_frames = ctx.audio_receiver.get_frames(timeout=0.1) # Reduced timeout
        if audio_frames:
            # Process the frames (e.g., transcribe)
            # In a real app, you'd likely want to buffer frames and process in chunks
            # Or send them to a separate processing thread/service
            st.info(f"Received {len(audio_frames)} audio frames.")

            # --- Transcription and Command (Example - needs more robust implementation) ---
            # This part is resource-intensive and might block the app if done directly here
            # Consider sending audio chunks to your backend asynchronously
            try:
                 # Example: Write frames to a temp WAV and send (inefficient for streaming)
                 with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav_file:
                     wav_writer = wave.open(tmp_wav_file.name, 'wb')
                     # These parameters must match the actual audio format from the browser
                     # You might need to inspect frames[0].format to get these correctly
                     # For simplicity, assuming common parameters:
                     wav_writer.setnchannels(1) # Mono
                     wav_writer.setsampwidth(2) # 2 bytes (16-bit audio)
                     wav_writer.setframerate(16000) # Common sample rate for speech
                     for frame in audio_frames:
                         # Ensure frame is in the expected format (e.g., int16)
                         # If frame.to_ndarray() gives float, convert and scale
                         audio_data = frame.to_ndarray().astype(np.int16).tobytes()
                         wav_writer.writeframes(audio_data)
                     wav_writer.close()

                 # Send the temporary file for transcription
                 files = {"file": open(tmp_wav_file.name, "rb")}
                 try:
                     transcribe_res = requests.post(TRANSCRIBE_URL, files=files)
                     if transcribe_res.status_code == 200:
                         transcript_data = transcribe_res.json()
                         transcript = transcript_data.get("transcript")
                         if transcript:
                             st.success(f"🗣️ Transcribed: {transcript}")
                             # Send transcript as command
                             command_res = requests.post(COMMAND_URL, json={"text_command": transcript})
                             if command_res.status_code == 200:
                                 command_data = command_res.json()
                                 st.info(f"🤖 GPT-4o: {command_data.get('spoken_text', 'No response.')}")
                             else:
                                 st.error(f"Command failed: {command_res.status_code}")
                                 st.error(f"Command response body: {command_res.text}")
                         else:
                              st.info("Transcription returned empty.")
                     else:
                         st.error(f"Transcription failed: {transcribe_res.status_code}")
                         st.error(f"Transcription response body: {transcribe_res.text}")
                 except requests.exceptions.RequestException as e:
                     st.error(f"Error during transcription or command: {e}")
                 finally:
                     # Clean up the temporary file
                     os.remove(tmp_wav_file.name)


            except Exception as e:
                st.error(f"Error processing audio frames: {e}")

    except av.TimeoutError:
        # This is expected if no frames are available within the timeout
        pass
    except Exception as e:
         st.error(f"An unexpected error occurred in audio receiver: {e}")

# Note: The real-time audio processing and API calls within the main Streamlit loop
# can easily block the app. For production, consider using background threads,
# queues, or sending the audio stream directly to a backend service for processing.
