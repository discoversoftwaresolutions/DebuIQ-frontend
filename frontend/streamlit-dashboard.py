import streamlit as st
import requests
import os
import difflib
from streamlit_ace import st_ace
# Import WebRtcMode for the fix and ClientSettings, AudioProcessorBase
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings, WebRtcMode
import soundfile as sf
import numpy as np
import av
import tempfile
import streamlit.components.v1 as components
from difflib import HtmlDiff
import json # Import json for parsing backend error responses
# import io # Needed if streaming bytes from memory

# 🌐 BACKEND URL
# This is the base URL for your backend service on Render.
# It is used to fetch the initial configuration endpoint URL.
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
# The specific endpoint for fetching all other API URLs from the backend config router
CONFIG_ENDPOINT_PATH = "/api/config" # Adjust if your config router prefix is different

# 🔱 Brand Header
st.set_page_config(page_title="DebugIQ – Autonomous Debugging", layout="wide")
st.title("🧠 DebugIQ")
st.markdown("**AI-Powered Trace Analysis, Patch Generation, QA, and Documentation**")

# --- Session State Initialization ---
# Use session state to preserve information across Streamlit reruns
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
if 'api_endpoints' not in st.session_state:
    st.session_state.api_endpoints = None # To store fetched backend endpoint URLs

# --- Fetch API Endpoints on Initial Load or Backend URL Change ---
# This connects the frontend to the backend by getting the correct API paths.
# This block runs only once unless session state is cleared or BACKEND_URL changes
if st.session_state.api_endpoints is None:
    config_url = f"{BACKEND_URL.rstrip('/')}{CONFIG_ENDPOINT_PATH}" # Construct full config URL
    st.info(f"Attempting to connect to backend at {BACKEND_URL} and fetch API configuration from {config_url}...")
    try:
        config_res = requests.get(config_url)
        config_res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        st.session_state.api_endpoints = config_res.json()
        st.success("✅ API configuration loaded successfully.")
        # Optional: Display fetched endpoints for debugging
        # st.sidebar.json(st.session_state.api_endpoints)
    except requests.exceptions.RequestException as e:
        st.error(f"**Failed to connect to backend or fetch API configuration.**")
        st.error(f"Please ensure the backend service is running at `{BACKEND_URL}` and the endpoint `{CONFIG_ENDPOINT_PATH}` is accessible.")
        st.error(f"Connection Error: {e}")
        # Stop the script execution if the backend is not reachable
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred while fetching API configuration: {e}")
        st.stop()

# --- Ensure API Endpoints are Available Before Proceeding ---
# If for some reason api_endpoints is still None after the block above, stop.
# This check is mostly a safeguard, as st.stop() should prevent reaching here if fetch failed.
if st.session_state.api_endpoints is None:
     st.error("API endpoints could not be loaded. Cannot proceed.")
     st.stop()

# 🔍 Upload Trace + Code Files
st.markdown("### Upload Files")
# Use a unique key for the file uploader to manage its state across reruns
uploaded_files = st.file_uploader()
    "Upload traceback (.txt) and source files (e.g., .py)",
    type=["txt", "py"], # Specify allowed types
    accept_multiple_files=True,
    key="file_uploader" # Unique key for this widget
