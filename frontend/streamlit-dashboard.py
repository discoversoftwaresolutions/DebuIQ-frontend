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

st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Autonomous Debugging Dashboard")

BACKEND_URL = os.getenv("BACKEND_URL", https://debugiq-backend.onrender.com")

@st.cache_data
def fetch_config():
    try:
        r = requests.get(f"{BACKEND_URL}/api/config")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        st.error(f"⚠️ Could not load config: {e}")
    return {}

config = fetch_config()
if config:
    st.sidebar.info(f"🔧 Voice Provider: {config.get('voice_provider', 'N/A')}")
    st.sidebar.info(f"🧠 Model: {config.get('model', 'N/A')}")

ANALYZE_URL = config.get("analyze", f"{BACKEND_URL}/debugiq/analyze")
QA_URL = config.get("qa", f"{BACKEND_URL}/qa/")
TRANSCRIBE_URL = config.get("voice_transcribe", f"{BACKEND_URL}/voice/transcribe")
COMMAND_URL = config.get("voice_command", f"{BACKEND_URL}/voice/command")

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
# === GitHub Repo Integration Sidebar ===
st.sidebar.markdown("### 📦 Load From GitHub Repo")
repo_url = st.sidebar.text_input("Public GitHub URL", placeholder="https://github.com/user/repo")

if repo_url:
    try:
        import re
        import base64

        match = re.match(r"https://github.com/([^/]+)/([^/]+)", repo_url.strip())
        if match:
            owner, repo = match.groups()
            branches_res = requests.get(f"https://api.github.com/repos/{owner}/{repo}/branches")
            if branches_res.status_code == 200:
                branches = [b["name"] for b in branches_res.json()]
                selected_branch = st.sidebar.selectbox("Branch", branches)

                # Directory navigator
                path_stack = st.session_state.get("github_path_stack", [""])
                current_path = "/".join([p for p in path_stack if p])

                content_res = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{current_path}?ref={selected_branch}"
                )

                if content_res.status_code == 200:
                    entries = content_res.json()
                    dirs = [e["name"] for e in entries if e["type"] == "dir"]
                    files = [e["name"] for e in entries if e["type"] == "file"]

                    dir_choice = st.sidebar.selectbox("📁 Navigate", [".."] + dirs)
                    if "github_path_stack" not in st.session_state:
                        st.session_state.github_path_stack = [""]

                    if dir_choice == ".." and len(path_stack) > 1:
                        st.session_state.github_path_stack.pop()
                        st.experimental_rerun()
                    elif dir_choice and dir_choice != "..":
                        st.session_state.github_path_stack.append(dir_choice)
                        st.experimental_rerun()

                    file_choice = st.sidebar.selectbox("📄 Files", files)
                    if file_choice:
                        file_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{selected_branch}/{current_path}/{file_choice}".rstrip("/")
                        file_content = requests.get(file_url).text

                        st.sidebar.success(f"Loaded: {file_choice}")
                        # Set the trace or source file based on extension
                        if file_choice.endswith(".txt"):
                            st.session_state.analysis_results["trace"] = file_content
                        else:
                            st.session_state.analysis_results["source_files_content"][file_choice] = file_content

            else:
                st.sidebar.error("❌ Invalid repo or cannot fetch branches.")
        else:
            st.sidebar.warning("Please enter a valid GitHub repo URL.")

    except Exception as e:
        st.sidebar.error(f"⚠️ GitHub Load Error: {e}")
