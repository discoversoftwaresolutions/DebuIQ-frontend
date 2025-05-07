import streamlit as st
import requests
import os
import difflib
from streamlit_ace import st_ace
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings
import soundfile as sf
import numpy as np
import av
import tempfile
import streamlit.components.v1 as components
from difflib_html import HtmlDiff

# 🌐 BACKEND URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
ANALYZE_URL = f"{BACKEND_URL}/debugiq/analyze"
QA_URL = f"{BACKEND_URL}/qa/"

# 🔱 Brand Header
st.set_page_config(page_title="DebugIQ – Autonomous Debugging", layout="wide")
st.title("🧠 DebugIQ")
st.markdown("**AI-Powered Trace Analysis, Patch Generation, QA, and Documentation**")

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

# 🔍 Upload Trace + Code Files
st.markdown("### Upload Files")
uploaded_files = st.file_uploader("Upload traceback (.txt) and source files", type=["txt", "py"], accept_multiple_files=True)

trace_content, source_files_content = None, {}
if uploaded_files:
    trace_file = next((f for f in uploaded_files if f.name.endswith(".txt")), None)
    trace_content = trace_file.getvalue().decode("utf-8") if trace_file else None
    source_files_content = {f.name: f.getvalue().decode("utf-8") for f in uploaded_files if not f.name.endswith(".txt")}
    st.session_state.analysis_results['trace'] = trace_content
    st.session_state.analysis_results['source_files_content'] = source_files_content

# --- Tabs: Patch, QA, Doc ---
tab1, tab2, tab3 = st.tabs(["🔧 Patch Analysis", "✅ QA", "📘 Docs"])

with tab1:
    st.subheader("Analyze & Generate Patch")
    if trace_content:
        if st.button("Run DebugIQ"):
            with st.spinner("Analyzing..."):
                try:
                    res = requests.post(ANALYZE_URL, json={
                        "trace": trace_content,
                        "language": "python",
                        "source_files": source_files_content
                    })
                    result = res.json()
                    st.session_state.analysis_results.update({
                        'patch': result.get("patch"),
                        'explanation': result.get("explanation"),
                        'doc_summary': result.get("doc_summary"),
                        'patched_file_name': result.get("patched_file_name"),
                        'original_patched_file_content': result.get("original_patched_file_content")
                    })
                    st.success("✅ Patch Ready")
                except Exception as e:
                    st.error(f"Error: {e}")

    patch = st.session_state.analysis_results['patch']
    if patch:
        st.markdown("### Patch Diff")
        diff_mode = st.radio("View Mode", ["Unified Text", "Visual HTML"], horizontal=True)
        original = st.session_state.analysis_results['original_patched_file_content']
        patched = patch
        if diff_mode == "Unified Text":
            diff = "\n".join(difflib.unified_diff(
                original.splitlines(), patched.splitlines(),
                fromfile="original", tofile="patched", lineterm=""
            ))
            st.code(diff, language="diff")
        else:
            html_diff = HtmlDiff().make_table(
                original.splitlines(), patched.splitlines(),
                "Original", "Patched", context=True, numlines=5
            )
            components.html(html_diff, height=400, scrolling=True)

        st.markdown("### Edit Patch")
        edited_patch = st_ace(value=patched, language="python", theme="monokai", key="patch_editor")

        st.markdown("### Explanation")
        st.text_area("LLM Explanation", value=st.session_state.analysis_results['explanation'], height=200)

        if st.button("Run QA on Edited Patch"):
            with st.spinner("Validating..."):
                qa_res = requests.post(QA_URL, json={
                    "trace": trace_content,
                    "patch": edited_patch,
                    "language": "python",
                    "source_files": source_files_content,
                    "patched_file_name": st.session_state.analysis_results['patched_file_name']
                })
                st.session_state.qa_result = qa_res.json()
                st.success("QA Complete")

with tab2:
    st.subheader("LLM + Static QA Results")
    result = st.session_state.qa_result
    if result:
        st.markdown("#### LLM Review")
        st.markdown(result.get("llm_qa_result", "No result."))

        st.markdown("#### Static Findings")
        for file, issues in result.get("static_analysis_result", {}).items():
            st.markdown(f"**{file}**")
            for i in issues:
                msg = f"{i.get('type', '')}: Line {i.get('line', '')} - {i.get('msg', '')}"
                st.text(msg)

with tab3:
    st.subheader("Auto-Generated Documentation")
    st.markdown(st.session_state.analysis_results['doc_summary'] or "No summary yet.")

# 🎙️ DebugIQ Voice Assistant (Optional)
with st.expander("🎙️ DebugIQ Voice Assistant (Optional)", expanded=False):
    audio_file = st.file_uploader("Upload voice command (.wav)", type=["wav"])
    if audio_file:
        st.audio(audio_file, format="audio/wav")
        files = {"file": ("voice.wav", audio_file.getvalue(), "audio/wav")}
        transcribe_res = requests.post(f"{BACKEND_URL}/voice/transcribe", files=files)

        if transcribe_res.ok:
            transcript = transcribe_res.json().get("transcript", "")
            st.success(f"🧠 You said: `{transcript}`")
            command_res = requests.post(f"{BACKEND_URL}/voice/command", json={"text_command": transcript})
            reply = command_res.json().get("spoken_text", "No response.")
            st.markdown(f"🔁 Response: `{reply}`")
            speak_res = requests.post(f"{BACKEND_URL}/voice/speak", json={"text_command": reply})
            if speak_res.ok:
                st.audio(speak_res.content, format="audio/wav")

    class AudioRecorder(AudioProcessorBase):
        def __init__(self):
            self.audio_frames = []
        def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
            self.audio_frames.append(frame.to_ndarray())
            return frame

    ctx = webrtc_streamer(
        key="voice-recorder",
        mode="sendonly",
        audio_receiver_size=1024,
        client_settings=ClientSettings(media_stream_constraints={"audio": True, "video": False}),
        audio_processor_factory=AudioRecorder
    )

    if ctx.audio_processor:
        st.info("🎙️ Speak now...")
        if st.button("Stop and Submit Voice"):
            audio_data = np.concatenate(ctx.audio_processor.audio_frames, axis=1).flatten().astype(np.int16)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                sf.write(tmpfile.name, audio_data, samplerate=48000, format="WAV")
                tmpfile.seek(0)
                files = {"file": ("live.wav", tmpfile.read(), "audio/wav")}
                transcribe_res = requests.post(f"{BACKEND_URL}/voice/transcribe", files=files)
                if transcribe_res.ok:
                    transcript = transcribe_res.json().get("transcript", "")
                    st.success(f"🧠 You said: `{transcript}`")
                    command_res = requests.post(f"{BACKEND_URL}/voice/command", json={"text_command": transcript})
                    reply = command_res.json().get("spoken_text", "No response.")
                    st.markdown(f"🔁 Response: `{reply}`")
                    speak_res = requests.post(f"{BACKEND_URL}/voice/speak", json={"text_command": reply})
                    if speak_res.ok:
                        st.audio(speak_res.content, format="audio/wav")
