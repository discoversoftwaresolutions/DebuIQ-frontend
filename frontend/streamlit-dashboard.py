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
uploaded_files = st.file_uploader(
    "Upload traceback (.txt) and source files (e.g., .py)",
    type=["txt", "py"], # Specify allowed types
    accept_multiple_files=True,
    key="file_uploader" # Unique key for this widget
)

trace_content, source_files_content = None, {}
if uploaded_files:
    # When new files are uploaded, reset the analysis and QA results
    # This ensures the UI clears old data for a new analysis
    st.session_state.analysis_results = {
        'trace': None,
        'patch': None,
        'explanation': None,
        'doc_summary': None,
        'patched_file_name': None,
        'original_patched_file_content': None,
        'source_files_content': {} # This will be overwritten below
    }
    st.session_state.qa_result = None # Clear previous QA results

    # Process uploaded files
    trace_file = next((f for f in uploaded_files if f.name.endswith(".txt")), None)
    trace_content = trace_file.getvalue().decode("utf-8") if trace_file else None

    # Filter and decode source files
    source_files_content = {}
    for f in uploaded_files:
        if not f.name.endswith(".txt"): # Process files that are not tracebacks
            try:
                source_files_content[f.name] = f.getvalue().decode("utf-8")
            except Exception as e:
                st.warning(f"Could not decode source file {f.name}: {e}")
                source_files_content[f.name] = f"Error decoding file: {e}" # Store error message

    # Store the processed content in session state
    st.session_state.analysis_results['trace'] = trace_content
    st.session_state.analysis_results['source_files_content'] = source_files_content

    # Provide user feedback on uploaded files
    if not trace_content and not source_files_content:
         st.warning("No valid traceback (.txt) or source files (.py) were uploaded.")
    else:
        if trace_content:
             st.info("Traceback (.txt) uploaded.")
        if source_files_content:
             st.info(f"Source files uploaded: {list(source_files_content.keys())}")


# Retrieve current content from session state for use in UI and API calls
current_trace_content = st.session_state.analysis_results['trace']
current_source_files_content = st.session_state.analysis_results['source_files_content']


# --- Tabs: Patch, QA, Doc ---
# Use unique keys for tabs if they contain stateful elements or complex logic
tab1, tab2, tab3 = st.tabs(["🔧 Patch Analysis", "✅ QA", "📘 Docs"])

with tab1:
    st.subheader("Analyze & Generate Patch")
    # The analysis button should only appear if there's content to analyze
    if current_trace_content or current_source_files_content:
        # Use a unique key for the analysis button
        if st.button("Run DebugIQ Analysis", key="run_analysis_button"):
            # Ensure required data is actually present before making the call
            if not current_trace_content and not current_source_files_content:
                 st.warning("Please upload files before running analysis.")
            else:
                with st.spinner("Analyzing code and generating patch..."):
                    try:
                        # Use the fetched analyze URL from session state
                        analyze_url = st.session_state.api_endpoints.get('analyze')

                        if not analyze_url:
                             st.error("Analyze API endpoint URL is not configured in the backend API configuration.")
                        else:
                            # Make the POST request to the backend analyze endpoint
                            res = requests.post(analyze_url, json={
                                "trace": current_trace_content,
                                "language": "python", # Assuming Python for now, could be a user input later
                                "source_files": current_source_files_content
                            })
                            res.raise_for_status() # Raise HTTPError for bad responses

                            # Process the successful JSON response
                            result = res.json()

                            # Update session state with results from backend analysis
                            st.session_state.analysis_results.update({
                                'patch': result.get("patch"),
                                'explanation': result.get("explanation"),
                                'doc_summary': result.get("doc_summary"),
                                # These should ideally be determined by the backend based on the analysis
                                'patched_file_name': result.get("patched_file_name", "N/A"),
                                'original_patched_file_content': result.get("original_patched_file_content", "# Original content not provided by backend")
                            })
                            st.success("✅ Analysis Complete! See Patch Diff and Explanation below.")

                    except requests.exceptions.RequestException as e:
                         st.error(f"Error during analysis request to backend.")
                         if e.response:
                             try:
                                 # Attempt to parse backend's JSON error response
                                 error_details = e.response.json()
                                 st.error(f"Backend Error: {error_details.get('detail', 'Unknown error')}")
                                 if 'errors' in error_details: # Display validation errors if present (FastAPI standard)
                                     st.markdown("<h6>Validation Errors:</h6>", unsafe_allow_html=True)
                                     st.json(error_details['errors'])
                             except json.JSONDecodeError:
                                 # If backend returned a non-JSON error response
                                 st.error(f"Backend returned non-JSON error: {e.response.text}")
                         else:
                             # Handle network errors or connection issues
                             st.error(f"Network Error: {e}")
                    except Exception as e:
                        # Catch any other unexpected errors during the process
                        st.error(f"An unexpected error occurred during analysis: {e}")


    # --- Display Analysis Results: Patch Diff, Editor, Explanation ---
    # Only display these sections if a patch was successfully generated and returned
    patch_content = st.session_state.analysis_results.get('patch')
    original_content = st.session_state.analysis_results.get('original_patched_file_content')
    patched_file_name = st.session_state.analysis_results.get('patched_file_name', 'File')
    explanation_content = st.session_state.analysis_results.get('explanation')

    if patch_content is not None and original_content is not None: # Ensure both are available for diff
        st.markdown("---") # Separator
        st.markdown("### Generated Patch")

        st.markdown("#### Patch Diff")
        # Use a unique key for the radio button
        diff_mode = st.radio("View Mode", ["Unified Text", "Visual HTML"], horizontal=True, key="diff_mode_radio")

        # Ensure content is split into lines for difflib
        original_lines = original_content.splitlines() if original_content else []
        patched_lines = patch_content.splitlines() if patch_content else []

        if diff_mode == "Unified Text":
            diff = "\n".join(difflib.unified_diff(
                original_lines, patched_lines,
                fromfile=f"a/{patched_file_name}", # Standard diff format
                tofile=f"b/{patched_file_name}",   # Standard diff format
                lineterm="" # Prevents extra newlines
            ))
            st.code(diff, language="diff")
        else:
            # Use HtmlDiff for visual comparison
            html_diff = HtmlDiff().make_table(
                original_lines, patched_lines,
                f"Original: {patched_file_name}",
                f"Patched: {patched_file_name}",
                context=True, # Show context lines
                numlines=5 # Number of context lines
            )
            # Display HTML content. Adjust height and scrolling as needed.
            components.html(html_diff, height=500, scrolling=True)

        st.markdown("#### Edit Patch")
        # Use streamlit-ace for an editable code area.
        # Use a key to maintain the editor's state across reruns.
        # The value should default to the generated patch if available.
        edited_patch = st_ace(
            value=patch_content, # Display the generated patch initially
            language="python", # Set language mode
            theme="monokai", # Set editor theme
            key="patch_editor", # Unique key for the ace editor
            height=400 # Set editor height
        )

        st.markdown("#### Explanation")
        # Display the LLM-generated explanation
        st.text_area(
            "LLM Explanation",
            value=explanation_content if explanation_content else 'No explanation provided yet.',
            height=200,
            key="explanation_textarea", # Unique key
            disabled=True # Make it read-only
        )

        # --- Button to Run QA on Edited Patch ---
        # This button is available if analysis was run and a patch exists
        if st.button("Run QA on Edited Patch", key="run_qa_button"):
            # Ensure required data is available before calling QA endpoint
            if not (current_trace_content or current_source_files_content):
                 st.warning("Please upload files first.")
            elif edited_patch is None: # st_ace might be loading
                 st.warning("Please wait for the patch editor to load.")
            else:
                 with st.spinner("Running QA on the edited patch..."):
                     try:
                         # Use the fetched QA URL from session state
                         # Assumes the config endpoint provides the correct full URL for the QA action
                         qa_url = st.session_state.api_endpoints.get('qa') # Check your config.py route name

                         if not qa_url:
                            st.error("QA API endpoint URL is not configured in the backend API configuration.")
                         else:
                             # Make the POST request to the backend QA endpoint
                             qa_res = requests.post(qa_url, json={
                                 "trace": current_trace_content,
                                 "patch": edited_patch, # Send the current content of the editor
                                 "language": "python", # Assuming Python
                                 "source_files": current_source_files_content,
                                 "patched_file_name": patched_file_name # Send the file name
                             })
                             qa_res.raise_for_status() # Raise HTTPError for bad responses

                             # Process the successful JSON response
                             st.session_state.qa_result = qa_res.json()
                             st.success("✅ QA Complete! See results in the QA tab.")

                     except requests.exceptions.RequestException as e:
                         st.error(f"Error during QA request to backend.")
                         if e.response:
                             try:
                                 # Attempt to parse backend's JSON error response
                                 error_details = e.response.json()
                                 st.error(f"Backend Error: {error_details.get('detail', 'Unknown error')}")
                                 if 'errors' in error_details: # Display validation errors
                                      st.markdown("<h6>Validation Errors:</h6>", unsafe_allow_html=True)
                                      st.json(error_details['errors'])
                             except json.JSONDecodeError:
                                 # If backend returned a non-JSON error response
                                 st.error(f"Backend returned non-JSON error: {e.response.text}")
                         else:
                             # Handle network errors or connection issues
                             st.error(f"Network Error: {e}")
                     except Exception as e:
                         # Catch any other unexpected errors
                         st.error(f"An unexpected error occurred during QA: {e}")

    elif current_trace_content or current_source_files_content:
         # Message displayed if files are uploaded but analysis hasn't run or failed
         st.info("Upload files and click 'Run DebugIQ Analysis' to generate a patch.")
    else:
         # Message displayed if no files are uploaded
         st.info("Upload traceback and source code files to begin analysis.")


with tab2:
    st.subheader("LLM + Static QA Results")
    qa_results = st.session_state.qa_result

    if qa_results:
        st.markdown("#### LLM Review")
        # Use .get for safety, provide default message
        llm_review = qa_results.get("llm_qa_result", "No LLM review provided.")
        st.markdown(llm_review) # Use markdown to render potential formatting

        st.markdown("#### Static Findings")
        # Use .get for safety, provide default empty dict
        static_findings = qa_results.get("static_analysis_result", {})

        if static_findings:
             for file, issues in static_findings.items():
                 st.markdown(f"**{file}**")
                 if issues:
                     # Display each static analysis issue
                     for i in issues:
                         issue_type = i.get('type', 'Issue')
                         line = i.get('line', 'N/A')
                         msg = i.get('msg', 'No message')
                         st.text(f"{issue_type}: Line {line} - {msg}")
                 else:
                      st.info(f"No static analysis issues found for {file}.")
        else:
            st.info("No static analysis results available.")
    else:
        st.info("Run 'Patch Analysis' and click 'Run QA on Edited Patch' to see QA results here.")


with tab3:
    st.subheader("Auto-Generated Documentation")
    # Display the documentation summary obtained from the analysis results
    doc_summary = st.session_state.analysis_results.get('doc_summary')

    if doc_summary:
        st.markdown("#### Analysis Summary Documentation")
        st.markdown(doc_summary) # Use markdown to render the summary
    else:
        st.info("No documentation summary available yet. Run analysis first.")

    # --- Optional: Button for More Detailed Docs if Backend Supports ---
    # doc_url = st.session_state.api_endpoints.get('doc') # Check your config.py route name
    # if doc_url:
    #     st.markdown("---")
    #     st.markdown("#### Generate Detailed Documentation")
    #     # This button would trigger a call to the /doc endpoint
    #     if st.button("Generate Detailed Docs for Uploaded Files", key="generate_detailed_docs"):
    #         if not (current_trace_content or current_source_files_content):
    #             st.warning("Please upload files first to generate detailed documentation.")
    #         else:
    #             with st.spinner("Generating detailed documentation..."):
    #                 try:
    #                     # Assuming doc endpoint takes source files content
    #                     doc_res = requests.post(doc_url, json={"source_files": current_source_files_content})
    #                     doc_res.raise_for_status()
    #                     detailed_docs_result = doc_res.json()
    #                     detailed_docs_content = detailed_docs_result.get("docs", "Could not generate detailed documentation.") # Adjust key based on your doc endpoint response
    #                     st.markdown("##### Generated Detailed Documentation")
    #                     st.markdown(detailed_docs_content) # Display the generated docs
    #                 except requests.exceptions.RequestException as e:
    #                     st.error(f"Error generating detailed docs: {e}")
    #                     if e.response:
    #                         st.text(e.response.text) # Display backend error text
    #                 except Exception as e:
    #                     st.error(f"An unexpected error occurred during detailed doc generation: {e}")


# 🎙️ DebugIQ Voice Assistant (Optional) Expander
with st.expander("🎙️ DebugIQ Voice Assistant (Optional)", expanded=False):
    st.markdown("Note: This section requires your backend's voice endpoints to be functional and correctly configured.")

    # Get voice endpoint URLs from fetched config
    voice_transcribe_url = st.session_state.api_endpoints.get('voice_transcribe')
    voice_command_url = st.session_state.api_endpoints.get('voice_command')
    voice_speak_url = st.session_state.api_endpoints.get('voice_speak')

    # Check if all necessary voice endpoints are available
    if not (voice_transcribe_url and voice_command_url and voice_speak_url):
         st.warning("Voice assistant endpoints are not configured in the backend API configuration. Please check your backend's `/api/config` output.")
    else:
        # --- Voice Command File Upload ---
        st.markdown("#### Upload Voice Command")
        audio_file_uploader = st.file_uploader(
            "Upload voice command (.wav)",
            type=["wav"], # Accept WAV files
            key="voice_uploader" # Unique key
        )

        if audio_file_uploader:
            st.audio(audio_file_uploader, format="audio/wav", key="uploaded_audio_player") # Display uploaded audio

            # Prepare file for request
            files = {"file": ("voice_command.wav", audio_file_uploader.getvalue(), "audio/wav")}

            with st.spinner("Transcribing uploaded audio..."):
                try:
                    # Make the POST request to the backend transcribe endpoint
                    transcribe_res = requests.post(voice_transcribe_url, files=files)
                    transcribe_res.raise_for_status() # Raise HTTPError for bad responses

                    transcript = transcribe_res.json().get("transcript", "")

                    if transcript:
                        st.success(f"🧠 You said: `{transcript}`")

                        # --- Process Transcribed Command ---
                        with st.spinner("Processing command..."):
                            try:
                                # Make the POST request to the backend command endpoint
                                command_res = requests.post(voice_command_url, json={"text_command": transcript})
                                command_res.raise_for_status() # Raise HTTPError for bad responses

                                reply = command_res.json().get("spoken_text", "No response provided by the command agent.")

                                if reply and reply != "No response provided by the command agent.":
                                     st.markdown(f"🔁 Response: `{reply}`")

                                     # --- Synthesize and Play Response ---
                                     with st.spinner("Synthesizing speech response..."):
                                         try:
                                             # Make the POST request to the backend speak endpoint
                                             speak_res = requests.post(voice_speak_url, json={"text_command": reply})
                                             speak_res.raise_for_status() # Raise HTTPError

                                             # Assuming speak_res.content is the raw audio data bytes
                                             st.audio(speak_res.content, format="audio/wav", key="synthesized_audio_player")

                                         except requests.exceptions.RequestException as e:
                                             st.error(f"Error synthesizing speech response from backend.")
                                             if e.response: st.text(e.response.text)
                                         except Exception as e:
                                             st.error(f"An unexpected error occurred during speech synthesis: {e}")
                                else:
                                    st.info("Command processed, but no speech response was generated by the backend.")

                            except requests.exceptions.RequestException as e:
                                st.error(f"Error processing command with backend.")
                                if e.response: st.text(e.response.text)
                            except Exception as e:
                                st.error(f"An unexpected error occurred during command processing: {e}")

                    else:
                        st.warning("Transcription was empty. Could not process command.")

                except requests.exceptions.RequestException as e:
                     st.error(f"Error during voice transcription request to backend.")
                     if e.response: st.text(e.response.text)
                except Exception as e:
                    st.error(f"An unexpected error occurred during transcription: {e}")


        st.markdown("---") # Separator

        # --- Live Voice Recording ---
        st.markdown("#### Live Voice Recording")

        class AudioRecorder(AudioProcessorBase):
            def __init__(self):
                self.audio_frames = []
            def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
                # Append audio data as numpy arrays
                self.audio_frames.append(frame.to_ndarray())
                return frame # Return the frame to allow potential chaining


        # Streamlit-webrtc component for live recording.
        # Use a unique key.
        ctx = webrtc_streamer(
            key="voice-recorder", # Unique key for this webrtc instance
            mode=WebRtcMode.SENDONLY, # Set mode to send only audio
            audio_receiver_size=1024, # Buffer size for audio frames
            client_settings=ClientSettings( # Configure browser media access
                media_stream_constraints={"audio": True, "video": False} # Request audio only
            ),
            audio_processor_factory=AudioRecorder, # Use our custom processor
            async_processing=True # Enable async processing for better performance
        )

        # Logic to process recorded audio after recording stops
        if ctx.audio_processor: # Check if the audio processor is active
            st.info("🎙️ Click 'Start' to begin recording. Click 'Stop' when done, then 'Stop and Submit Voice'.")
            # The Stop button is provided by streamlit-webrtc when recording is active

            # This button appears after clicking the Stop button provided by streamlit-webrtc
            if st.button("Stop and Submit Voice", key="submit_recorded_voice_button"):
                 if not ctx.audio_processor.audio_frames:
                      st.warning("No audio frames were recorded.")
                 else:
                    with st.spinner("Processing recorded audio..."):
                        try:
                            # Concatenate recorded frames and convert to int16 WAV format
                            audio_data = np.concatenate(ctx.audio_processor.audio_frames, axis=1).flatten().astype(np.int16)

                            # Use a temporary file to save the recorded audio as WAV
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                                sf.write(tmpfile.name, audio_data, samplerate=48000, format="WAV") # Save as WAV
                                temp_audio_path = tmpfile.name # Store path for cleanup

                            # Read the temporary file's content for the API request
                            with open(temp_audio_path, "rb") as f:
                                files = {"file": ("live_recording.wav", f.read(), "audio/wav")}

                            # --- Send Recorded Audio to Transcribe Endpoint ---
                            transcribe_res = requests.post(voice_transcribe_url, files=files)
                            transcribe_res.raise_for_status() # Raise HTTPError

                            transcript = transcribe_res.json().get("transcript", "")

                            if transcript:
                                st.success(f"🧠 You said: `{transcript}`")

                                # --- Process Transcribed Command ---
                                with st.spinner("Processing command..."):
                                    try:
                                        # Send transcript to the backend command endpoint
                                        command_res = requests.post(voice_command_url, json={"text_command": transcript})
                                        command_res.raise_for_status() # Raise HTTPError

                                        reply = command_res.json().get("spoken_text", "No response provided by the command agent.")

                                        if reply and reply != "No response provided by the command agent.":
                                            st.markdown(f"🔁 Response: `{reply}`")

                                            # --- Synthesize and Play Response ---
                                            with st.spinner("Synthesizing speech response..."):
                                                try:
                                                    # Send reply text to the backend speak endpoint
                                                    speak_res = requests.post(voice_speak_url, json={"text_command": reply})
                                                    speak_res.raise_for_status() # Raise HTTPError

                                                    # Assuming speak_res.content is the raw audio data bytes
                                                    st.audio(speak_res.content, format="audio/wav", key="live_synthesized_audio_player")

                                                except requests.exceptions.RequestException as e:
                                                    st.error(f"Error synthesizing speech response from backend.")
                                                    if e.response: st.text(e.response.text)
                                                except Exception as e:
                                                    st.error(f"An unexpected error occurred during speech synthesis: {e}")
                                        else:
                                            st.info("Command processed, but no speech response was generated by the backend.")

                                    except requests.exceptions.RequestException as e:
                                         st.error(f"Error processing command with backend.")
                                         if e.response: st.text(e.response.text)
                                    except Exception as e:
                                        st.error(f"An unexpected error occurred during command processing: {e}")
                            else:
                                st.warning("Transcription was empty. Could not process command.")

                            # Clear recorded frames after processing to reset recorder
                            ctx.audio_processor.audio_frames = []

                        except requests.exceptions.RequestException as e:
                            st.error(f"Error during voice transcription request to backend.")
                            if e.response: st.text(e.response.text)
                        except Exception as e:
                           st.error(f"An unexpected error occurred during recording processing or transcription: {e}")
                        finally:
                            # Ensure the temporary audio file is cleaned up
                            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                                try:
                                    os.remove(temp_audio_path)
                                except OSError as e:
                                    # Print error if cleanup fails
                                    st.warning(f"Could not remove temporary audio file {temp_audio_path}: {e}")
