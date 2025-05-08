import streamlit as st
import requests
import os
import difflib
from streamlit_ace import st_ace
# Import WebRtcMode here for the fix
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings, WebRtcMode
import soundfile as sf
import numpy as np
import av
import tempfile
import streamlit.components.v1 as components
from difflib import HtmlDiff
import json # Import json for better error handling

# 🌐 BACKEND URL
# This is now only used to fetch the initial configuration endpoint URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
CONFIG_URL = f"{BACKEND_URL}/api/config" # Endpoint to get all other API URLs

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
if 'api_endpoints' not in st.session_state:
    st.session_state.api_endpoints = None # Store fetched backend endpoint URLs

# --- Fetch API Endpoints on Load ---
# This ensures the frontend knows the correct paths from the backend config
if st.session_state.api_endpoints is None:
    st.info(f"Connecting to backend at {BACKEND_URL} and fetching API configuration...")
    try:
        config_res = requests.get(CONFIG_URL)
        config_res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        st.session_state.api_endpoints = config_res.json()
        st.success("✅ API configuration loaded.")
        # You can print the fetched endpoints during development to verify
        # st.json(st.session_state.api_endpoints)
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend or fetch API configuration from {CONFIG_URL}. Please ensure the backend is running and accessible.")
        st.error(f"Error: {e}")
        st.stop() # Stop execution if we can't connect to the backend


# 🔍 Upload Trace + Code Files
st.markdown("### Upload Files")
uploaded_files = st.file_uploader("Upload traceback (.txt) and source files", type=["txt", "py"], accept_multiple_files=True, key="file_uploader")

trace_content, source_files_content = None, {}
if uploaded_files:
    # Clear previous results when new files are uploaded
    st.session_state.analysis_results = {
        'trace': None,
        'patch': None,
        'explanation': None,
        'doc_summary': None,
        'patched_file_name': None,
        'original_patched_file_content': None,
        'source_files_content': {}
    }
    st.session_state.qa_result = None # Clear QA results too

    trace_file = next((f for f in uploaded_files if f.name.endswith(".txt")), None)
    trace_content = trace_file.getvalue().decode("utf-8") if trace_file else None
    source_files_content = {f.name: f.getvalue().decode("utf-8") for f in uploaded_files if not f.name.endswith(".txt")}

    # Store the uploaded content in session state
    st.session_state.analysis_results['trace'] = trace_content
    st.session_state.analysis_results['source_files_content'] = source_files_content

    if not trace_content and not source_files_content:
         st.warning("Please upload at least a traceback or source file.")
    elif trace_content:
         st.info("Traceback uploaded.")
    if source_files_content:
         st.info(f"Source files uploaded: {list(source_files_content.keys())}")


# Retrieve content from session state after upload
current_trace_content = st.session_state.analysis_results['trace']
current_source_files_content = st.session_state.analysis_results['source_files_content']


# --- Tabs: Patch, QA, Doc ---
tab1, tab2, tab3 = st.tabs(["🔧 Patch Analysis", "✅ QA", "📘 Docs"])

with tab1:
    st.subheader("Analyze & Generate Patch")
    # Only enable analysis if trace or source files are provided
    if current_trace_content or current_source_files_content:
        if st.button("Run DebugIQ Analysis"): # Changed button text slightly
            # Ensure required data is available before calling backend
            if not current_trace_content and not current_source_files_content:
                 st.warning("Please upload files before running analysis.")
            else:
                with st.spinner("Analyzing..."):
                    try:
                        # Use the fetched analyze URL
                        analyze_url = st.session_state.api_endpoints.get('analyze')
                        if not analyze_url:
                             st.error("Analyze API endpoint URL is not configured in the backend.")
                        else:
                            res = requests.post(analyze_url, json={
                                "trace": current_trace_content,
                                "language": "python", # Assuming Python for now based on original code
                                "source_files": current_source_files_content
                            })
                            res.raise_for_status() # Raise HTTPError for bad responses
                            result = res.json()

                            # Update session state with results from backend
                            st.session_state.analysis_results.update({
                                'patch': result.get("patch"),
                                'explanation': result.get("explanation"),
                                'doc_summary': result.get("doc_summary"),
                                # Note: patched_file_name and original_patched_file_content
                                # should ideally come from the backend analysis
                                'patched_file_name': result.get("patched_file_name", "N/A"),
                                'original_patched_file_content': result.get("original_patched_file_content", "# Original content not provided by backend")
                            })
                            st.success("✅ Analysis Complete!")

                            # Optional: If a doc summary is available, trigger docs display
                            if st.session_state.analysis_results.get('doc_summary'):
                                 # You could potentially make a call to the /doc endpoint here
                                 # if it requires separate processing, or just display the summary
                                 pass # Display is handled in tab3


                    except requests.exceptions.RequestException as e:
                         st.error(f"Error during analysis request to backend.")
                         if e.response:
                             try:
                                 error_details = e.response.json()
                                 st.error(f"Backend Error: {error_details.get('detail', 'Unknown error')}")
                                 # Display validation errors if present
                                 if 'errors' in error_details:
                                     st.json(error_details['errors'])
                             except json.JSONDecodeError:
                                 st.error(f"Backend returned non-JSON error: {e.response.text}")
                         else:
                             st.error(f"Network Error: {e}")
                    except Exception as e:
                        st.error(f"An unexpected error occurred during analysis: {e}")


    # Display Analysis Results
    patch = st.session_state.analysis_results.get('patch') # Use .get for safety
    original_content = st.session_state.analysis_results.get('original_patched_file_content') # Use .get

    if patch and original_content is not None: # Only show diff if patch and original content are available
        st.markdown("### Patch Diff")
        diff_mode = st.radio("View Mode", ["Unified Text", "Visual HTML"], horizontal=True, key="diff_mode")

        # Ensure original content is treated as lines
        original_lines = original_content.splitlines() if original_content else []
        patched_lines = patch.splitlines() if patch else []


        if diff_mode == "Unified Text":
            diff = "\n".join(difflib.unified_diff(
                original_lines, patched_lines,
                fromfile=st.session_state.analysis_results.get('patched_file_name', 'original'),
                tofile=st.session_state.analysis_results.get('patched_file_name', 'patched'),
                lineterm=""
            ))
            st.code(diff, language="diff")
        else:
            html_diff = HtmlDiff().make_table(
                original_lines, patched_lines,
                st.session_state.analysis_results.get('patched_file_name', 'Original'),
                st.session_state.analysis_results.get('patched_file_name', 'Patched'),
                context=True, numlines=5
            )
            components.html(html_diff, height=400, scrolling=True)

        st.markdown("### Edit Patch")
        # Ensure the editor shows the latest patch from state or user edits
        edited_patch = st_ace(value=patch, language="python", theme="monokai", key="patch_editor")

        st.markdown("### Explanation")
        # Use .get for safety
        st.text_area("LLM Explanation", value=st.session_state.analysis_results.get('explanation', 'No explanation provided yet.'), height=200)

        # Button to trigger QA on the edited patch
        # Ensure required data is present (trace, source files, and now an edited patch)
        if current_trace_content or current_source_files_content: # Need context
             if st.button("Run QA on Edited Patch"):
                 if edited_patch is None: # st_ace might return None initially
                      st.warning("Please wait for the patch editor to load or ensure a patch exists.")
                 else:
                     with st.spinner("Running QA..."):
                         try:
                             # Use the fetched QA URL
                             # Assuming the config endpoint provides a direct QA endpoint URL
                             qa_url = st.session_state.api_endpoints.get('qa') # Check your config.py route name
                             # If your QA endpoint expects /qa/analyze-patch specifically,
                             # the config should provide the full path, or you construct it:
                             # qa_analyze_patch_url = f"{st.session_state.api_endpoints.get('qa_base_url')}/analyze-patch" # Example if config provides base
                             # Let's assume 'qa' endpoint in config is the correct full path

                             if not qa_url:
                                st.error("QA API endpoint URL is not configured in the backend.")
                             else:
                                 qa_res = requests.post(qa_url, json={
                                     "trace": current_trace_content,
                                     "patch": edited_patch, # Send the user's edited patch
                                     "language": "python", # Assuming Python
                                     "source_files": current_source_files_content,
                                     "patched_file_name": st.session_state.analysis_results.get('patched_file_name', 'N/A')
                                 })
                                 qa_res.raise_for_status() # Raise HTTPError for bad responses
                                 st.session_state.qa_result = qa_res.json()
                                 st.success("✅ QA Complete!")

                         except requests.exceptions.RequestException as e:
                             st.error(f"Error during QA request to backend.")
                             if e.response:
                                 try:
                                     error_details = e.response.json()
                                     st.error(f"Backend Error: {error_details.get('detail', 'Unknown error')}")
                                     if 'errors' in error_details:
                                         st.json(error_details['errors'])
                                 except json.JSONDecodeError:
                                     st.error(f"Backend returned non-JSON error: {e.response.text}")
                             else:
                                 st.error(f"Network Error: {e}")
                         except Exception as e:
                             st.error(f"An unexpected error occurred during QA: {e}")


with tab2:
    st.subheader("LLM + Static QA Results")
    result = st.session_state.qa_result
    if result:
        st.markdown("#### LLM Review")
        st.markdown(result.get("llm_qa_result", "No result."))

        st.markdown("#### Static Findings")
        static_findings = result.get("static_analysis_result", {})
        if static_findings:
             for file, issues in static_findings.items():
                 st.markdown(f"**{file}**")
                 if issues:
                     for i in issues:
                         msg = f"{i.get('type', '')}: Line {i.get('line', '')} - {i.get('msg', '')}"
                         st.text(msg)
                 else:
                      st.text("No static analysis issues found for this file.")
        else:
            st.info("No static analysis results available.")


with tab3:
    st.subheader("Auto-Generated Documentation")
    # Display the doc summary from the analysis results
    doc_summary = st.session_state.analysis_results.get('doc_summary')
    if doc_summary:
        st.markdown(doc_summary)
    else:
        st.info("No documentation summary available yet. Run analysis first.")

    # Optional: If backend has a dedicated /doc endpoint for more detailed docs
    # doc_url = st.session_state.api_endpoints.get('doc')
    # if doc_url and st.button("Generate Detailed Docs"):
    #     with st.spinner("Generating detailed documentation..."):
    #         try:
    #             # Assuming doc endpoint takes source files or a specific file
    #             doc_res = requests.post(doc_url, json={"source_files": current_source_files_content})
    #             doc_res.raise_for_status()
    #             detailed_docs = doc_res.json().get("docs", "Could not generate detailed docs.")
    #             st.markdown("#### Detailed Documentation")
    #             st.markdown(detailed_docs)
    #         except requests.exceptions.RequestException as e:
    #             st.error(f"Error generating detailed docs: {e}")


# 🎙️ DebugIQ Voice Assistant (Optional)
with st.expander("🎙️ DebugIQ Voice Assistant (Optional)", expanded=False):
    st.markdown("Note: This section requires your backend's voice endpoints to be functional.")

    # Ensure voice endpoints are available from config
    voice_transcribe_url = st.session_state.api_endpoints.get('voice_transcribe')
    voice_command_url = st.session_state.api_endpoints.get('voice_command')
    voice_speak_url = st.session_state.api_endpoints.get('voice_speak')

    if not (voice_transcribe_url and voice_command_url and voice_speak_url):
         st.warning("Voice assistant endpoints are not configured in the backend API configuration.")
    else:
        # File upload for voice commands
        audio_file = st.file_uploader("Upload voice command (.wav)", type=["wav"], key="voice_uploader")
        if audio_file:
            st.audio(audio_file, format="audio/wav")
            files = {"file": ("voice.wav", audio_file.getvalue(), "audio/wav")}
            with st.spinner("Transcribing uploaded audio..."):
                try:
                    transcribe_res = requests.post(voice_transcribe_url, files=files)
                    transcribe_res.raise_for_status()
                    transcript = transcribe_res.json().get("transcript", "")
                    st.success(f"🧠 You said: `{transcript}`")

                    if transcript: # Only send command if transcription was successful
                        with st.spinner("Processing command..."):
                            try:
                                command_res = requests.post(voice_command_url, json={"text_command": transcript})
                                command_res.raise_for_status()
                                reply = command_res.json().get("spoken_text", "No response.")
                                st.markdown(f"🔁 Response: `{reply}`")

                                if reply and reply != "No response.": # Only speak if there's a meaningful reply
                                     with st.spinner("Synthesizing speech..."):
                                         try:
                                             speak_res = requests.post(voice_speak_url, json={"text_command": reply})
                                             speak_res.raise_for_status()
                                             # Assuming speak_res.content is the audio data
                                             st.audio(speak_res.content, format="audio/wav")
                                         except requests.exceptions.RequestException as e:
                                             st.error(f"Error synthesizing speech: {e}")
                                         except Exception as e:
                                             st.error(f"An unexpected error occurred during speech synthesis: {e}")
                            except requests.exceptions.RequestException as e:
                                 st.error(f"Error processing command: {e}")
                            except Exception as e:
                                st.error(f"An unexpected error occurred processing command: {e}")
                except requests.exceptions.RequestException as e:
                     st.error(f"Error during voice transcription: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred during transcription: {e}")


        st.markdown("---") # Separator for live recording

        # Live voice recording using streamlit-webrtc
        class AudioRecorder(AudioProcessorBase):
            def __init__(self):
                self.audio_frames = []
            def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
                self.audio_frames.append(frame.to_ndarray())
                return frame

        # Fixed the mode parameter here
        ctx = webrtc_streamer(
            key="voice-recorder",
            mode=WebRtcMode.SENDONLY, # <--- FIX: Use the Enum member
            audio_receiver_size=1024,
            client_settings=ClientSettings(media_stream_constraints={"audio": True, "video": False}),
            audio_processor_factory=AudioRecorder,
            async_processing=True # Recommended for audio processing
        )

        if ctx.audio_processor:
            st.info("🎙️ Speak now...")
            if st.button("Stop and Submit Voice"):
                 if not ctx.audio_processor.audio_frames:
                      st.warning("No audio recorded.")
                 else:
                    with st.spinner("Processing recorded audio..."):
                        try:
                            # Concatenate and convert audio data
                            audio_data = np.concatenate(ctx.audio_processor.audio_frames, axis=1).flatten().astype(np.int16)
                            # Use tempfile securely
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                                sf.write(tmpfile.name, audio_data, samplerate=48000, format="WAV")
                                temp_audio_path = tmpfile.name

                            # Read the temporary file for upload
                            with open(temp_audio_path, "rb") as f:
                                files = {"file": ("live.wav", f.read(), "audio/wav")}

                            # Send to transcribe endpoint
                            transcribe_res = requests.post(voice_transcribe_url, files=files)
                            transcribe_res.raise_for_status()
                            transcript = transcribe_res.json().get("transcript", "")
                            st.success(f"🧠 You said: `{transcript}`")

                            if transcript: # Only send command if transcription successful
                                 # Send transcript to command endpoint
                                 with st.spinner("Processing command..."):
                                     try:
                                         command_res = requests.post(voice_command_url, json={"text_command": transcript})
                                         command_res.raise_for_status()
                                         reply = command_res.json().get("spoken_text", "No response.")
                                         st.markdown(f"🔁 Response: `{reply}`")

                                         if reply and reply != "No response.": # Only speak if meaningful reply
                                             # Send reply to speak endpoint
                                             with st.spinner("Synthesizing speech..."):
                                                 try:
                                                     speak_res = requests.post(voice_speak_url, json={"text_command": reply})
                                                     speak_res.raise_for_status()
                                                     st.audio(speak_res.content, format="audio/wav")
                                                 except requests.exceptions.RequestException as e:
                                                     st.error(f"Error synthesizing speech: {e}")
                                                 except Exception as e:
                                                    st.error(f"An unexpected error occurred during speech synthesis: {e}")
                                     except requests.exceptions.RequestException as e:
                                         st.error(f"Error processing command: {e}")
                                     except Exception as e:
                                        st.error(f"An unexpected error occurred processing command: {e}")
                            # Clear recorded frames after processing
                            ctx.audio_processor.audio_frames = []
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error during voice transcription: {e}")
                        except Exception as e:
                           st.error(f"An unexpected error occurred during recording processing or transcription: {e}")
                        finally:
                            # Clean up the temporary file
                            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                                os.remove(temp_audio_path)

        # Stop button appears automatically when ctx.audio_processor is not None
