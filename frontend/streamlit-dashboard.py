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
from difflib import HtmlDiff
import streamlit.components.v1 as components

# Basic setup
st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Dashboard")

# Environment & URLs
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
ANALYZE_URL = f"{BACKEND_URL}/debugiq/analyze"
QA_URL = f"{BACKEND_URL}/qa/"
TRANSCRIBE_URL = f"{BACKEND_URL}/voice/transcribe"
COMMAND_URL = f"{BACKEND_URL}/voice/command"

# Session state
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

# File uploader
uploaded_files = st.file_uploader("Upload traceback (.txt) and source files", type=["txt", "py"], accept_multiple_files=True)

trace_content, source_files_content = None, {}
if uploaded_files:
    for file in uploaded_files:
        content = file.getvalue().decode("utf-8")
        if file.name.endswith(".txt"):
            trace_content = content
        else:
            source_files_content[file.name] = content

    st.session_state.analysis_results['trace'] = trace_content
    st.session_state.analysis_results['source_files_content'] = source_files_content

# Tabs
tab1, tab2, tab3 = st.tabs(["🔧 Patch", "✅ QA", "📘 Docs"])

# Patch tab
with tab1:
    if st.button("Analyze with DebugIQ"):
        res = requests.post(ANALYZE_URL, json={
            "trace": st.session_state.analysis_results['trace'],
            "language": "python",
            "config": {},
            "source_files": st.session_state.analysis_results['source_files_content']
        })
        result = res.json()
        st.session_state.analysis_results.update({
            'patch': result.get("patch"),
            'explanation': result.get("explanation"),
            'doc_summary': result.get("doc_summary"),
            'patched_file_name': result.get("patched_file_name"),
            'original_patched_file_content': result.get("original_patched_file_content")
        })

    st.markdown("### Patch Diff")
    diff = "
".join(difflib.unified_diff(
        st.session_state.analysis_results['original_patched_file_content'].splitlines(),
        st.session_state.analysis_results['patch'].splitlines(),
        fromfile="original", tofile="patched", lineterm=""
    ))
    st.code(diff, language="diff")

    st.markdown("### Edit Patch")
    edited_patch = st_ace(
        value=st.session_state.analysis_results['patch'],
        language="python",
        theme="monokai",
        height=300,
        key="patch_editor"
    )

    st.markdown("### Explanation")
    st.text_area("Patch Explanation", value=st.session_state.analysis_results['explanation'], height=150)

# Mic Debug + GPT-4o Command
st.markdown("### 🎙️ Voice Assistant")

ctx = webrtc_streamer(
    key="voice-transcribe",
    mode=WebRtcMode.SENDONLY,
    client_settings=ClientSettings(
        media_stream_constraints={"audio": True, "video": False},
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    ),
    audio_receiver_size=1024
)

if ctx and ctx.audio_receiver:
    frames = ctx.audio_receiver.get_frames(timeout=1)
    if frames:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            wav_bytes = b''.join([frame.to_ndarray().tobytes() for frame in frames])
            f.write(wav_bytes)
            f.flush()
            files = {"file": open(f.name, "rb")}
            r = requests.post(TRANSCRIBE_URL, files=files)
            if r.ok:
                transcript = r.json().get("transcript")
                st.success(f"🗣️ Transcribed: {transcript}")
                r2 = requests.post(COMMAND_URL, json={"text_command": transcript})
                if r2.ok:
                    st.info(f"🤖 Response: {r2.json().get('spoken_text')}")
