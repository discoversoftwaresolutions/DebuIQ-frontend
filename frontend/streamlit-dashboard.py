import streamlit as st
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, ClientSettings

st.set_page_config(page_title="DebugIQ – Voice Test", layout="wide")
st.title("🎙️ DebugIQ Voice Test")

st.markdown("This is a minimal test to confirm streamlit-webrtc is working.")

with st.expander("Microphone (streamlit-webrtc test)", expanded=True):
    st.info("Speak to the mic to test streamlit-webrtc setup.")
    ctx = webrtc_streamer(
        key="key",
        client_settings=ClientSettings(
            media_stream_constraints={"audio": True, "video": False},
            rtc_configuration={ "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}] }
        ),
        sendback_audio=False
    )
