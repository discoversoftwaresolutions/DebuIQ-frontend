# Generate the updated `streamlit-dashboard.py` with the autonomous workflow tab wired in
from pathlib import Path

streamlit_dashboard_code = '''
import streamlit as st
import requests
import os
from screens.AutonomousWorkflowTab import *  # This imports the new tab

# Set Streamlit layout
st.set_page_config(page_title="DebugIQ Dashboard", layout="wide")
st.title("🧠 DebugIQ Autonomous Debugging Dashboard")

# Backend Base URL
BACKEND_URL = os.getenv("BACKEND_URL", "https://autonomous-debug.onrender.com")
st.session_state["BACKEND_URL"] = BACKEND_URL

# Tabs Layout
tab1, tab2, tab3, tab4 = st.tabs(["🔧 Patch", "✅ QA", "📘 Docs", "🧠 Autonomy"])

# --- PATCH TAB ---
with tab1:
    st.subheader("Patch Analysis")
    st.markdown("🛠️ Placeholder for patch analysis UI...")

# --- QA TAB ---
with tab2:
    st.subheader("Quality Assurance")
    st.markdown("✅ Placeholder for QA results and test analysis...")

# --- DOCS TAB ---
with tab3:
    st.subheader("Auto-Generated Documentation")
    st.markdown("📘 Placeholder for documentation review...")

# --- AUTONOMOUS TAB ---
with tab4:
    st.subheader("Autonomous Workflow Engine")
    show()  # This is the entry point from AutonomousWorkflowTab
'''.strip()

streamlit_dashboard_path = Path("/mnt/data/DebugIQ-frontend/frontend/streamlit-dashboard.py")
streamlit_dashboard_path.write_text(streamlit_dashboard_code + "\n")

streamlit_dashboard_path
