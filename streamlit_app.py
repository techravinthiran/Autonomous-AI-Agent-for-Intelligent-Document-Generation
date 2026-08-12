"""
Streamlit Frontend for Autonomous AI Agent
User-friendly interface for document generation
"""

import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# ─── Page Setup ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Autonomous AI Agent",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state
if "api_url" not in st.session_state:
    st.session_state.api_url = API_URL

st.title("🤖 Autonomous AI Agent for Intelligent Document Generation")
st.markdown("---")

# ─── Main Content ───────────────────────────────────────────────────────────────
st.header("📝 Generate Document from Natural Language Request")

col1, col2 = st.columns([3, 1])

with col1:
    user_request = st.text_area(
        "Enter your request",
        placeholder="Example: Create a project plan for launching a new CRM software product for mid-size B2B companies",
        height=150,
        help="Describe the document you want to generate in natural language"
    )

with col2:
    st.write("")
    st.write("")
    generate_btn = st.button("🚀 Generate Document", type="primary", use_container_width=True)

# ─── Session State ───────────────────────────────────────────────────────────────
if "response" not in st.session_state:
    st.session_state.response = None

# ─── Generate Document ───────────────────────────────────────────────────────────
if generate_btn:
    if not user_request.strip():
        st.error("⚠️ Please enter a request")
    elif len(user_request) < 10:
        st.error("⚠️ Request is too short. Please provide more detail (minimum 10 characters)")
    elif len(user_request) > 2000:
        st.error("⚠️ Request is too long (maximum 2000 characters)")
    else:
        with st.spinner("🔄 Processing your request... This may take a moment."):
            try:
                response = requests.post(
                    f"{st.session_state.api_url}/agent",
                    json={"request": user_request},
                    timeout=300
                )
                
                if response.status_code == 200:
                    st.session_state.response = response.json()
                    st.success("✅ Document generated successfully!")
                else:
                    st.error(f"❌ Error: {response.status_code} - {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to the API. Make sure the FastAPI server is running.")
            except requests.exceptions.Timeout:
                st.error("❌ Request timed out. Please try again.")
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")

# ─── Display Results ─────────────────────────────────────────────────────────────
if st.session_state.response:
    response_data = st.session_state.response
    
    st.markdown("---")
    st.header("📊 Results")
    
    # Document Info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Document Type", response_data["document_type"])
    with col2:
        st.metric("Total Steps", response_data["total_steps"])
    with col3:
        st.metric("Completed Steps", response_data["completed_steps"])
    
    st.markdown("---")
    
    # Task List
    st.subheader("📋 Generated Tasks")
    for task in response_data["task_list"]:
        status_emoji = {
            "done": "✅",
            "running": "🔄",
            "pending": "⏳",
            "failed": "❌"
        }.get(task["status"], "❓")
        
        with st.expander(f"{status_emoji} Task {task['id']}: {task['title']}"):
            st.write(f"**Description:** {task['description']}")
            st.write(f"**Status:** {task['status'].upper()}")
    
    st.markdown("---")
    
    # Assumptions
    if response_data.get("assumptions_made"):
        st.subheader("💡 Assumptions Made")
        for assumption in response_data["assumptions_made"]:
            st.write(f"• {assumption}")
        st.markdown("---")
    
    # Reflection
    st.subheader("🔍 Self-Check / Reflection")
    st.info(response_data["reflection"])
    
    st.markdown("---")
    
    # Download Button
    st.subheader("📥 Download Document")
    document_url = f"{st.session_state.api_url}{response_data['document_url']}"
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("📄 Download Word Document", type="primary"):
            try:
                doc_response = requests.get(document_url)
                if doc_response.status_code == 200:
                    st.download_button(
                        label="💾 Save Document",
                        data=doc_response.content,
                        file_name=response_data["document_filename"],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                else:
                    st.error("Failed to download document")
            except Exception as e:
                st.error(f"Error downloading document: {str(e)}")
    
    with col2:
        st.write(f"Filename: `{response_data['document_filename']}`")
    
    # Clear button
    st.markdown("---")
    if st.button("🗑️ Clear Results"):
        st.session_state.response = None
        st.rerun()

# ─── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("Autonomous AI Agent for Intelligent Document Generation")
