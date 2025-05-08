# DebugIQ-frontend/streamlit-dashboard.py
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
uploaded_files = st.file_uploader(
    "Upload traceback (.txt) and source files (e.g., .py)",
    type=["txt", "py"], # Specify allowed types
    accept_multiple_files=True,
    key="file_uploader" # Unique key for this widget
)

trace_content, source_files_content = None, {}
# Check if uploaded_files is not None and is a list (it's a list when files are uploaded)
if uploaded_files is not None and len(uploaded_files) > 0:
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
                source_files_content[f.name] = f"Error decoding file: {e}" # Store error message or handle differently

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
# These variables reflect the state *after* potential upload processing
current_trace_content = st.session_state.analysis_results['trace']
current_source_files_content = st.session_state.analysis_results['source_files_content']


# --- Tabs: Patch, QA, Doc ---
# Use unique keys for tabs if they contain stateful elements or complex logic
tab1, tab2, tab3 = st.tabs(["🔧 Patch Analysis", "✅ QA", "📘 Docs"], key="main_tabs")

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
                            # Using a timeout is good practice for production APIs
                            res = requests.post(
                                analyze_url,
                                json={
                                    "trace": current_trace_content,
                                    "language": "python", # Assuming Python for now, could be a user input later
                                    "source_files": current_source_files_content
                                },
                                timeout=120 # Increased example timeout for analysis
                            )
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

                            # Optional: If a doc summary is available, trigger docs display
                            if st.session_state.analysis_results.get('doc_summary'):
                                 # This simply updates the session state; display is in tab3
                                 pass


                    except requests.exceptions.Timeout:
                        st.error(f"Analysis request timed out after {120} seconds.")
                    except requests.exceptions.RequestException as e:
                         st.error(f"Error during analysis request to backend.")

                         # --- START DEBUGGING BACKEND ERROR RESPONSE ---
                         st.sidebar.write("--- Debugging Backend Error Response ---")
                         st.sidebar.write(f"Exception object: {e}")
                         st.sidebar.write(f"Response available (e.response): {e.response is not None}")
                         if e.response is not None:
                             st.sidebar.write(f"Response status code: {e.response.status_code}")
                             try:
                                 # Attempt to print headers (might fail on some objects)
                                 st.sidebar.write(f"Response headers: {dict(e.response.headers)}")
                             except Exception as header_e:
                                  st.sidebar.write(f"Error getting headers: {header_e}")

                             try:
                                 # Read the response text once
                                 response_text = e.response.text
                                 st.sidebar.write(f"Raw response text (first 500 chars): {response_text[:500]}...")
                                 st.sidebar.write(f"Raw response text length: {len(response_text)}")

                                 # Attempt to parse response text as JSON
                                 # This is where FastAPI puts validation errors for 422s and other details
                                 error_details = json.loads(response_text)
                                 st.sidebar.write("Successfully parsed response text as JSON.")
                                 st.sidebar.write("Full parsed JSON:")
                                 st.sidebar.json(error_details) # Display the full JSON in the sidebar

                                 # Now proceed with displaying formatted error details based on JSON content
                                 # Check for standard FastAPI validation errors first
                                 if 'errors' in error_details and isinstance(error_details['errors'], list):
                                      st.markdown("<h6>Validation Errors:</h6>", unsafe_allow_html=True)
                                      # Display the list of validation error dictionaries
                                      st.json(error_details['errors'])
                                 elif 'detail' in error_details: # Handle other 'detail' messages (e.g., from HTTPExceptions, or simple messages)
                                      st.markdown("<h6>Backend Detail:</h6>", unsafe_allow_html=True)
                                      # Attempt to display detail, might be a string or another structure
                                      try:
                                          st.json(error_details['detail']) # Try displaying as JSON first
                                      except:
                                          st.write(error_details['detail']) # Fallback to st.write if not JSON serializable

                                 else:
                                      st.markdown("<h6>Backend Response JSON:</h6>", unsafe_allow_html=True)
                                      st.json(error_details) # Display whatever JSON was returned


                             except json.JSONDecodeError:
                                 # If backend returned a non-JSON error response (unexpected for 422 from FastAPI validation)
                                 st.error(f"Backend returned non-JSON error response. Raw text:")
                                 st.code(response_text) # Display the raw non-JSON response text
                             except Exception as parse_e:
                                  # Catch any other errors during parsing/display after reading text
                                  st.error(f"DEBUG: An error occurred trying to parse/display backend error response: {parse_e}")
                         else:
                             # This block should theoretically not be hit for a status code > 0, but keeping for robustness
                             st.error(f"Network Error: {e} (No HTTP response body received for status {e.response.status_code})")
                     else:
                         # Handle network errors or connection issues where no response was received at all
                         st.error(f"Network Error: {e} (No HTTP response received)")
                     st.sidebar.write("--- End Debugging Backend Error Response ---")
                     # --- END DEBUGGING BACKEND ERROR RESPONSE ---

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
        # Use a unique key for the radio button to preserve selection
        diff_mode = st.radio("View Mode", ["Unified Text", "Visual HTML"], horizontal=True, key="diff_mode_radio")

        # Ensure content is split into lines for difflib, handle potential None/empty strings
        original_lines = original_content.splitlines() if isinstance(original_content, str) else []
        patched_lines = patch_content.splitlines() if isinstance(patch_content, str) else []

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
            # Use a unique key for the HTML component
            components.html(html_diff, height=500, scrolling=True, key="html_diff_component")

        st.markdown("#### Edit Patch")
        # Use streamlit-ace for an editable code area.
        # Use a key to maintain the editor's state across reruns.
        # The value should default to the generated patch if available.
        edited_patch = st_ace(
            value=patch_content if patch_content is not None else "", # Display the generated patch initially or empty string
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
        # This button is available if analysis was run and a patch exists (and implicitly files were uploaded)
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
                             qa_res = requests.post(
                                 qa_url,
                                 json={
                                     "trace": current_trace_content,
                                     "patch": edited_patch, # Send the current content of the editor
                                     "language": "python", # Assuming Python
                                     "source_files": current_source_files_content,
                                     "patched_file_name": patched_file_name # Send the file name
                                 },
                                 timeout=120 # Example timeout
                             )
                             qa_res.raise_for_status() # Raise HTTPError for bad responses

                             # Process the successful JSON response
                             st.session_state.qa_result = qa_res.json()
                             st.success("✅ QA Complete! See results in the QA tab.")

                     except requests.exceptions.Timeout:
                         st.error(f"QA request timed out after {120} seconds.")
                     except requests.exceptions.RequestException as e:
                         st.error(f"Error during QA request to backend.")
                         # QA error handling can be similar to analysis error handling
                         if e.response:
                             try:
                                 error_details = e.response.json()
                                 st.error(f"Backend Error: {error_details.get('detail', 'Unknown error')}")
                                 if 'errors' in error_details:
                                      st.markdown("<h6>Validation Errors:</h6>", unsafe_allow_html=True)
                                      st.json(error_details['errors'])
                                 elif 'detail' in error_details:
                                      st.markdown("<h6>Backend Detail:</h6>", unsafe_allow_html=True)
                                      st.json(error_details['detail'])
                                 else:
                                      st.markdown("<h6>Backend Response JSON:</h6>", unsafe_allow_html=True)
                                      st.json(error_details)
                             except json.JSONDecodeError:
                                 st.error(f"Backend returned non-JSON error. Response text:")
                                 st.code(e.response.text)
                             except Exception as parse_e:
                                 st.error(f"DEBUG: An error occurred trying to parse/display backend QA error response: {parse_e}")
                         else:
                             st.error(f"Network Error: {e} (No HTTP response received)")
                     except Exception as e:
                         st.error(f"An unexpected error occurred during QA: {e}")

    # Messages to guide the user if analysis results are not displayed
    elif current_trace_content or current_source_files_content:
         st.info("Upload files and click 'Run DebugIQ Analysis' to generate a patch.")
    else:
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
             if isinstance(static_findings, dict): # Ensure it's a dictionary
                 for file, issues in static_findings.items():
                     st.markdown(f"**{file}**")
                     if issues and isinstance(issues, list): # Ensure issues is a list
                         # Display each static analysis issue
                         for i in issues:
                             if isinstance(i, dict): # Ensure issue is a dict
                                 issue_type = i.get('type', 'Issue')
                                 line = i.get('line', 'N/A')
                                 msg = i.get('msg', 'No message')
                                 st.text(f"{issue_type}: Line {line} - {msg}") # Corrected message format
                             else:
                                 st.warning(f"Unexpected format for issue in {file}: {i}")
                     elif issues is not None: # Handle empty list or non-list if not None
                          st.info(f"No static analysis issues found for {file}.")
             else: # Handle if static_analysis_result is not a dict
                 st.warning(f"Unexpected format for static analysis results: {static_findings}")
                 st.json(static_findings) # Display raw data if not dict
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
    #                     doc_res = requests.post(
    #                          doc_url,
    #                          json={"source_files": current_source_files_content},
    #                          timeout=120
    #                     )
    #                     doc_res.raise_for_status()
    #                     detailed_docs_result = doc_res.json()
    #                     # Adjust key based on your doc endpoint response, provide default
    #                     detailed_docs_content = detailed_docs_result.get("docs", "Could not generate detailed documentation.")
    #                     st.markdown("##### Generated Detailed Documentation")
    #                     st.markdown(detailed_docs_content) # Display the generated docs
    #                 except requests.exceptions.Timeout:
    #                     st.error(f"Detailed docs generation request timed out after {120} seconds.")
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
         st.markdown("---") # Add a separator if voice is not configured
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
            # GetValue() reads the file content. Ensure filename and content type are correct.
            files = {"file": ("voice_command.wav", audio_file_uploader.getvalue(), "audio/wav")}

            with st.spinner("Transcribing uploaded audio..."):
                try:
                    # Make the POST request to the backend transcribe endpoint
                    transcribe_res = requests.post(voice_transcribe_url, files=files, timeout=120) # Increased timeout
                    transcribe_res.raise_for_status() # Raise HTTPError for bad responses

                    transcript = transcribe_res.json().get("transcript", "")

                    if transcript:
                        st.success(f"🧠 You said: `{transcript}`")

                        # --- Process Transcribed Command ---
                        with st.spinner("Processing command..."):
                            try:
                                # Make the POST request to the backend command endpoint
                                command_res = requests.post(voice_command_url, json={"text_command": transcript}, timeout=120) # Increased timeout
                                command_res.raise_for_status() # Raise HTTPError for bad responses

                                reply = command_res.json().get("spoken_text", "No response provided by the command agent.")

                                if reply and reply != "No response provided by the command agent.":
                                     st.markdown(f"🔁 Response: `{reply}`")

                                     # --- Synthesize and Play Response ---
                                     with st.spinner("Synthesizing speech response..."):
                                         try:
                                             # Make the POST request to the backend speak endpoint
                                             # Timeout might be longer for synthesis
                                             speak_res = requests.post(voice_speak_url, json={"text_command": reply}, timeout=180) # Increased timeout
                                             speak_res.raise_for_status() # Raise HTTPError

                                             # Assuming speak_res.content is the raw audio data bytes (e.g., WAV bytes)
                                             st.audio(speak_res.content, format="audio/wav", key="synthesized_audio_player")

                                         except requests.exceptions.Timeout:
                                              st.error(f"Speech synthesis request timed out after {180} seconds.")
                                         except requests.exceptions.RequestException as e:
                                             st.error(f"Error synthesizing speech response from backend.")
                                             if e.response: st.text(e.response.text)
                                         except Exception as e:
                                             st.error(f"An unexpected error occurred during speech synthesis: {e}")
                                else:
                                    st.info("Command processed, but no speech response was generated by the backend.")

                            except requests.exceptions.Timeout:
                                st.error(f"Command processing request timed out after {120} seconds.")
                            except requests.exceptions.RequestException as e:
                                 st.error(f"Error processing command with backend.")
                                 if e.response: st.text(e.response.text)
                            except Exception as e:
                                st.error(f"An unexpected error occurred during command processing: {e}")

                    else:
                        st.warning("Transcription was empty. Could not process command.")

                except requests.exceptions.Timeout:
                    st.error(f"Voice transcription request timed out after {120} seconds.")
                except requests.exceptions.RequestException as e:
                     st.error(f"Error during voice transcription request to backend.")
                     if e.response: st.text(e.response.text)
                except Exception as e:
                    st.error(f"An unexpected error occurred during transcription: {e}")


        st.markdown("---") # Separator for live recording

        # --- Live Voice Recording ---
        st.markdown("#### Live Voice Recording")

        class AudioRecorder(AudioProcessorBase):
            def __init__(self):
                # Initialize list to store audio frames from the browser
                self.audio_frames = []
            def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
                # Append audio data as numpy arrays to the list
                self.audio_frames.append(frame.to_ndarray())
                return frame # Return the frame to allow potential chaining


        # Streamlit-webrtc component for live recording.
        # Use a unique key.
        ctx = webrtc_streamer(
            key="voice-recorder", # Unique key for this webrtc instance
            mode=WebRtcMode.SENDONLY, # Set mode to send only audio from browser to processor
            audio_receiver_size=1024, # Buffer size for audio frames
            client_settings=ClientSettings( # Configure browser media access permissions
                media_stream_constraints={"audio": True, "video": False} # Request audio input only, no video
            ),
            audio_processor_factory=AudioRecorder, # Specify our custom audio processor class
            async_processing=True # Enable asynchronous processing for better performance
        )

        # Logic to process recorded audio after recording stops and button is clicked
        if ctx.audio_processor: # Check if the audio processor instance is active (recording is possible)
            st.info("🎙️ Click 'Start' to begin recording. Click the 'Stop' button provided by Streamlit-webrtc when done, then click 'Stop and Submit Voice'.")
            # The 'Stop' button is automatically displayed by streamlit-webrtc when recording is active.

            # This button appears after clicking the Stop button provided by streamlit-webrtc
            # Use a unique key.
            if st.button("Stop and Submit Voice", key="submit_recorded_voice_button"):
                 if not ctx.audio_processor.audio_frames: # Check if any audio was actually recorded
                      st.warning("No audio frames were recorded.")
                 else:
                    with st.spinner("Processing recorded audio..."):
                        try:
                            # Concatenate recorded frames (list of numpy arrays) and convert to 16-bit integer format (standard for WAV)
                            audio_data = np.concatenate(ctx.audio_processor.audio_frames, axis=1).flatten().astype(np.int16)

                            # Use a temporary file to save the recorded audio as a WAV file
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                                # Write the numpy audio data to the temporary WAV file
                                sf.write(tmpfile.name, audio_data, samplerate=48000, format="WAV") # Save as WAV with specified sample rate
                                temp_audio_path = tmpfile.name # Store the path to the temporary file for cleanup

                            # Read the content of the temporary file to prepare for the API request
                            with open(temp_audio_path, "rb") as f:
                                # Prepare the file payload for the requests.post call
                                files = {"file": ("live_recording.wav", f.read(), "audio/wav")}

                            # --- Send Recorded Audio to Transcribe Endpoint ---
                            transcribe_res = requests.post(voice_transcribe_url, files=files, timeout=120) # Increased timeout
                            transcribe_res.raise_for_status() # Raise HTTPError if transcription fails

                            # Get the transcript from the JSON response
                            transcript = transcribe_res.json().get("transcript", "")

                            if transcript: # Proceed only if transcription is not empty
                                st.success(f"🧠 You said: `{transcript}`")

                                # --- Process Transcribed Command ---
                                with st.spinner("Processing command..."):
                                    try:
                                        # Send the transcribed text command to the backend command endpoint
                                        command_res = requests.post(voice_command_url, json={"text_command": transcript}, timeout=120) # Increased timeout
                                        command_res.raise_for_status() # Raise HTTPError if command processing fails

                                        reply = command_res.json().get("spoken_text", "No response provided by the command agent.")

                                        if reply and reply != "No response provided by the command agent.": # Only speak if there's a meaningful reply
                                            st.markdown(f"🔁 Response: `{reply}`")

                                            # --- Synthesize and Play Response ---
                                            with st.spinner("Synthesizing speech response..."):
                                                try:
                                                    # Send the reply text to the backend speak endpoint
                                                    # Timeout might be longer for synthesis depending on backend TTS
                                                    speak_res = requests.post(voice_speak_url, json={"text_command": reply}, timeout=180) # Increased timeout
                                                    speak_res.raise_for_status() # Raise HTTPError if synthesis fails

                                                    # Assuming speak_res.content is the raw audio data bytes (e.g., WAV bytes)
                                                    st.audio(speak_res.content, format="audio/wav", key="live_synthesized_audio_player")

                                                except requests.exceptions.Timeout:
                                                     st.error(f"Speech synthesis request timed out after {180} seconds.")
                                                except requests.exceptions.RequestException as e:
                                                    st.error(f"Error synthesizing speech response from backend.")
                                                    if e.response: st.text(e.response.text)
                                                except Exception as e:
                                                   st.error(f"An unexpected error occurred during speech synthesis: {e}")
                                        else:
                                            st.info("Command processed, but no speech response was generated by the backend.")

                                    except requests.exceptions.Timeout:
                                        st.error(f"Command processing request timed out after {120} seconds.")
                                    except requests.exceptions.RequestException as e:
                                         st.error(f"Error processing command with backend.")
                                         if e.response: st.text(e.response.text)
                                    except Exception as e:
                                        st.error(f"An unexpected error occurred during command processing: {e}")
                            else:
                                st.warning("Transcription was empty. Could not process command.")

                            # Clear recorded frames after processing to reset the AudioRecorder for the next recording
                            ctx.audio_processor.audio_frames = []

                        except requests.exceptions.Timeout:
                            st.error(f"Voice transcription request timed out after {120} seconds.")
                        except requests.exceptions.RequestException as e:
                            st.error(f"Error during voice transcription request to backend.")
                            if e.response: st.text(e.response.text)
                        except Exception as e:
                           st.error(f"An unexpected error occurred during recording processing or transcription: {e}")
                        finally:
                            # Ensure the temporary audio file is cleaned up regardless of success or failure
                            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                                try:
                                    os.remove(temp_audio_path)
                                except OSError as e:
                                    # Log a warning if cleanup fails, but don't stop the app
                                    st.warning(f"Could not remove temporary audio file {temp_audio_path}: {e}")
