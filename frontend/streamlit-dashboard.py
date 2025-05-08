import streamlit as st
import requests
import os
import difflib
from streamlit_ace import st_ace
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings, WebRtcMode
import soundfile as sf
import numpy as np
import av
import tempfile
import streamlit.components.v1 as components
from difflib import HtmlDiff

# 🌐 BACKEND URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
ANALYZE_URL = f"{BACKEND_URL}/debugiq/analyze"
QA_URL = f"{BACKEND_URL}/qa/"

# 🔱 Brand Header
st.set_page_config(page_title="DebugIQ – Autonomous Debugging", layout="wide")
st.title("🧠 DebugIQ")
st.markdown("**AI-Powered Trace Analysis, Patch Generation, QA, Documentation & Voice**")

# Initialize Session State
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
