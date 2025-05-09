import streamlit as st
import requests
import os
import difflib
import tempfile
from streamlit_ace import st_ace
from streamlit_webrtc import webrtc_streamer, ClientSettings, WebRtcMode
from difflib import HtmlDiff
import streamlit.components.v1 as components

# Set page config
st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Autonomous Debugging Dashboard")

# Backend endpoints
BACKEND_URL = os.getenv("BACKEND_URL",  https://debugiq-backend.onrender.com)
QA_URL = f"{BACKEND_URL}/qa/"
TRANSCRIBE_URL = f"{BACKEND_URL}/voice/transcribe"
COMMAND_URL = f"{BACKEND_URL}/voice/command"

# Session setup
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

# Upload section
uploaded_files = st.file_uploader("📄 Upload traceback (.txt) + source files", type=["txt", "py"], accept_multiple_files=True)

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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔧 Patch", "✅ QA", "📘 Docs", "📥 Issue Inbox", "🔁 Workflow Status"])

# --- PATCH TAB ---
with tab1:
    st.subheader("Traceback Analysis + Patch")
    if st.button("🧠 Run DebugIQ Analysis"):
        with st.spinner("Analyzing with GPT-4o..."):
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
            st.success("✅ Patch generated.")

    if st.session_state.analysis_results['patch']:
        st.markdown("### 🔍 Patch Diff")
        original = st.session_state.analysis_results['original_patched_file_content']
        patched = st.session_state.analysis_results['patch']
        html_diff = HtmlDiff().make_table(
            original.splitlines(), patched.splitlines(),
            "Original", "Patched", context=True, numlines=3
        )
        components.html(html_diff, height=400, scrolling=True)

        st.markdown("### ✏️ Edit Patch")
        edited_patch = st_ace(
            value=patched,
            language="python",
            theme="monokai",
            height=300,
            key="editor"
        )

        st.markdown("### 💬 Explanation")
        st.text_area("Patch Explanation", value=st.session_state.analysis_results['explanation'], height=150)

# --- QA TAB ---
with tab2:
    st.subheader("Run Quality Assurance on Patch")
    if st.button("🛡️ Run QA on Patch"):
        qa_res = requests.post(QA_URL, json={
            "trace": st.session_state.analysis_results['trace'],
            "patch": st.session_state.analysis_results['patch'],
            "language": "python",
            "source_files": st.session_state.analysis_results['source_files_content'],
            "patched_file_name": st.session_state.analysis_results['patched_file_name']
        })
        qa_data = qa_res.json()
        st.session_state.qa_result = qa_data
        st.success("✅ QA complete")

    if st.session_state.qa_result:
        st.markdown("### LLM Review")
        st.markdown(st.session_state.qa_result.get("llm_qa_result", "No LLM feedback."))
        st.markdown("### Static Analysis")
        st.json(st.session_state.qa_result.get("static_analysis_result", {}))

# --- DOCS TAB ---
with tab3:
    st.subheader("📘 Auto-Generated Documentation")
    st.markdown(st.session_state.analysis_results.get("doc_summary", "No documentation available."))

# --- ISSUE INBOX TAB ---
with tab4:
    st.subheader("📥 Autonomous Issue Inbox")
    try:
        inbox = requests.get(f"{BACKEND_URL}/issues/inbox").json()
        for issue in inbox.get("issues", []):
            with st.expander(f"Issue {issue.get('id')} - {issue.get('classification')} [{issue.get('status')}]"):
                st.json(issue)
                if st.button(f"▶️ Trigger Workflow for {issue.get('id')}", key=issue.get("id")):
                    r = requests.post(f"{BACKEND_URL}/workflow/run", json={"issue_id": issue.get("id")})
                    st.success(f"Triggered: {r.status_code}")
    except Exception as e:
        st.error(f"Failed to load inbox: {e}")

# --- WORKFLOW STATUS TAB ---
with tab5:
    st.subheader("🔁 Live Workflow Timeline")
    try:
        status = requests.get(f"{BACKEND_URL}/workflow/status").json()
        st.json(status)
    except Exception as e:
        st.error(f"Failed to load workflow status: {e}")

# --- 🎙️ VOICE ASSISTANT ---
st.markdown("## 🎙️ DebugIQ Voice Agent")
ctx = webrtc_streamer(
    key="voice",
    mode=WebRtcMode.SENDONLY,
    client_settings=ClientSettings(
        media_stream_constraints={"audio": True, "video": False},
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    ),
    audio_receiver_size=256
)

if ctx and ctx.audio_receiver:
    frames = ctx.audio_receiver.get_frames(timeout=1)
    if frames:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            wav_data = b"".join([frame.to_ndarray().tobytes() for frame in frames])
            f.write(wav_data)
            f.flush()
            files = {"file": open(f.name, "rb")}
            r = requests.post(TRANSCRIBE_URL, files=files)
            if r.ok:
                transcript = r.json().get("transcript")
                st.success(f"🗣️ Transcribed: {transcript}")
                r2 = requests.post(COMMAND_URL, json={"text_command": transcript})
                if r2.ok:
                    st.info(f"🤖 GPT-4o: {r2.json().get('spoken_text')}")
