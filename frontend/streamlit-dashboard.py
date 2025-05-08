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
