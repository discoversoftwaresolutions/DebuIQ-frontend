# ------------------------ DebugIQ Production Streamlit Dashboard ------------------------
# Combines Autonomous Debugging Workflow + Manual Upload + Voice Commands

import streamlit as st
import requests
import os
import tempfile
import difflib
from streamlit_ace import st_ace
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings, WebRtcMode
import numpy as np
import av

st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Autonomous Debugging UI")

BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
ANALYZE_URL = f"{BACKEND_URL}/debugiq/analyze"
QA_URL = f"{BACKEND_URL}/qa/"
TRANSCRIBE_URL = f"{BACKEND_URL}/voice/transcribe"
COMMAND_URL = f"{BACKEND_URL}/voice/command"

# Session state
if 'current_issue' not in st.session_state:
    st.session_state.current_issue = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = {}

# Sidebar metrics
st.sidebar.header("📊 System Metrics")
try:
    metrics = requests.get(f"{BACKEND_URL}/metrics").json()
    st.sidebar.metric("Autonomous Fix Rate", f"{metrics['fix_success_rate']}%")
    st.sidebar.metric("Avg Time to Fix", f"{metrics['avg_fix_time']}s")
    st.sidebar.metric("Top Failure Stage", metrics["most_common_failure"])
except Exception:
    st.sidebar.error("Unable to load metrics.")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗂️ Issue Inbox", "🧠 Manual Scan", "🤖 Workflow Queue",
    "⚠️ Review Needed", "📘 Issue Detail"
])

# ---------------------- Tab 1: Inbox -----------------------
with tab1:
    st.subheader("New Issues (Inbox)")
    try:
        inbox = requests.get(f"{BACKEND_URL}/issues/inbox").json()
        for issue in inbox:
            with st.expander(f"Issue {issue['id']} – {issue['priority']}"):
                st.markdown(f"- **Tags**: {', '.join(issue['tags'])}")
                st.markdown(f"- **Status**: {issue['status']}")
                if st.button("🔍 View", key=f"view_{issue['id']}"):
                    st.session_state.current_issue = issue
    except:
        st.error("Failed to fetch inbox.")

# ---------------------- Tab 2: Manual Debugging -----------------------
with tab2:
    st.subheader("📄 Upload Traceback & Source Files")
    uploaded_files = st.file_uploader("Upload .txt and .py files", type=["txt", "py"], accept_multiple_files=True)

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

    if st.button("🧠 Run Manual Patch Suggestion"):
        with st.spinner("Analyzing with GPT..."):
            res = requests.post(ANALYZE_URL, json={
                "trace": trace_content,
                "language": "python",
                "config": {},
                "source_files": source_files_content
            })
            if res.ok:
                result = res.json()
                st.session_state.analysis_results.update(result)
                st.success("Patch generated.")
            else:
                st.error("Patch generation failed.")

    if 'patch' in st.session_state.analysis_results:
        st.subheader("🔍 Patch Diff")
        original = st.session_state.analysis_results.get('original_patched_file_content', '')
        patched = st.session_state.analysis_results['patch']
        diff = difflib.HtmlDiff().make_table(
            original.splitlines(), patched.splitlines(),
            "Original", "Patched", context=True, numlines=3
        )
        st.components.v1.html(diff, height=400, scrolling=True)

        st.subheader("✏️ Edit Patch")
        st_ace(value=patched, language="python", theme="monokai", height=300, key="editor")

        st.subheader("💬 Explanation")
        st.text_area("Patch Explanation", value=st.session_state.analysis_results.get("explanation", ""), height=150)

    st.subheader("🛡️ QA Validation")
    if st.button("Run QA"):
        qa_res = requests.post(QA_URL, json={
            "trace": trace_content,
            "patch": st.session_state.analysis_results.get("patch"),
            "language": "python",
            "source_files": source_files_content,
            "patched_file_name": st.session_state.analysis_results.get("patched_file_name")
        })
        if qa_res.ok:
            qa_data = qa_res.json()
            st.json(qa_data)
        else:
            st.error("QA failed.")

# ---------------------- Tab 3: Workflow Queue -----------------------
with tab3:
    st.subheader("Autonomous Workflow Queue")
    try:
        queue = requests.get(f"{BACKEND_URL}/workflow/status").json()
        for job in queue:
            st.markdown(f"- **{job['issue_id']}** – `{job['current_stage']}` → {job['status']}")
    except:
        st.error("Failed to load workflow queue.")

# ---------------------- Tab 4: Issues Needing Review -----------------------
with tab4:
    st.subheader("Blocked / Review Required")
    try:
        blockers = requests.get(f"{BACKEND_URL}/issues/blocked").json()
        for item in blockers:
            st.warning(f"Issue {item['id']} – {item['reason']}")
    except:
        st.error("Failed to load attention-needed list.")

# ---------------------- Tab 5: Detailed Issue -----------------------
with tab5:
    if st.session_state.current_issue:
        issue = st.session_state.current_issue
        st.header(f"Issue {issue['id']} Details")
        timeline = requests.get(f"{BACKEND_URL}/issues/{issue['id']}/timeline").json()
        for step in timeline:
            st.markdown(f"- **{step['step']}**: {step['status']}")
        st.markdown("---")

        st.subheader("Diagnosis")
        diag = issue.get("diagnosis", {})
        st.markdown(f"- **Root Cause**: {diag.get('root_cause')}")
        st.markdown(f"- **Confidence**: {diag.get('confidence')}")

        st.subheader("Patch")
        patch = issue.get("patch", {})
        st.code(patch.get("diff", ""), language="python")
        st.markdown(patch.get("validation_summary", "No validation summary."))

        if st.button("✅ Approve Patch"):
            requests.post(f"{BACKEND_URL}/workflow/approve_patch", json={"issue_id": issue["id"]})

        if st.button("❌ Reject Patch"):
            reason = st.text_input("Rejection Reason")
            requests.post(f"{BACKEND_URL}/workflow/reject_patch", json={"issue_id": issue["id"], "reason": reason})
    else:
        st.info("Select an issue in the Inbox to view it here.")

# ---------------------- Persistent Voice Control -----------------------
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
