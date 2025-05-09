import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, ClientSettings
import av
import requests
import tempfile

# Your Gemini voice endpoint
VOICE_API_URL = "https://debugiq-backend.onrender.com/voice/interactive"

def show_voice_assistant_tab():
    st.subheader("🎙️ DebugIQ Voice Agent (Gemini)")
    st.markdown("Speak to the agent. It responds with voice only. Use it to ask about patches, triage, QA, or PRs.")

    ctx = webrtc_streamer(
        key="voice",
        mode=WebRtcMode.SENDONLY,
        client_settings=ClientSettings(
            media_stream_constraints={"audio": True, "video": False},
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
        ),
        audio_receiver_size=1024,
    )

    if ctx and ctx.audio_receiver:
        frames = ctx.audio_receiver.get_frames(timeout=3)
        if frames:
            st.info("🎤 Voice received. Processing...")
            pcm_data = b"".join([frame.to_ndarray().tobytes() for frame in frames])
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                tmp_wav.write(pcm_data)
                tmp_wav.flush()

                try:
                    with open(tmp_wav.name, "rb") as f:
                        files = {"file": f}
                        response = requests.post(VOICE_API_URL, files=files)
                        if response.status_code == 200:
                            st.success("✅ Voice response from Gemini:")
                            st.audio(response.content, format="audio/wav")
                        else:
                            st.error(f"Gemini voice call failed: {response.status_code}")
                            st.text(response.text)
                except Exception as e:
                    st.error(f"Error communicating with Gemini voice agent: {e}")
