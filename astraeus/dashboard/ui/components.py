"""
Reusable UI components for the ASTRAEUS dashboard.
"""

from __future__ import annotations

import streamlit as st

def render_floating_chat() -> None:
    """
    Renders a floating AI chat interface using a popover.
    Provides context-aware interaction based on session_state.
    """
    if "ai_chat_messages" not in st.session_state:
        st.session_state.ai_chat_messages = [
            {"role": "assistant", "content": "Hello! I am ASTRAEUS AI. How can I help you analyze this workspace?"}
        ]

    # CSS to inject to make the next container float at the bottom right.
    st.markdown(
        """
        <style>
        /* Anchor styling: we use :has selector to target the container with the popover */
        div.element-container:has(.floating-chat-anchor) + div.element-container {
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 9999;
        }

        /* Style the button to look like a prominent floating action button */
        div.element-container:has(.floating-chat-anchor) + div.element-container > div > button {
            border-radius: 30px !important;
            height: 50px !important;
            padding: 0 20px !important;
            background-color: #8B5CF6 !important; /* Soft purple */
            color: #ffffff !important;
            border: none !important;
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4) !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            transition: all 0.3s ease !important;
        }

        div.element-container:has(.floating-chat-anchor) + div.element-container > div > button:hover {
            background-color: #7C3AED !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 16px rgba(139, 92, 246, 0.6) !important;
            color: #ffffff !important;
        }
        
        /* The popover container window */
        div[data-testid="stPopoverBody"] {
            background-color: #0F172A !important;
            border: 1px solid #1E293B !important;
            border-radius: 12px !important;
            width: 400px !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5) !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Hidden anchor to target the following popover
    st.markdown('<div class="floating-chat-anchor"></div>', unsafe_allow_html=True)

    with st.popover("💬 AI Assistant"):
        st.markdown("### ASTRAEUS AI")
        st.caption("I can see your workspace context. Ask me anything!")
        
        # Message history container
        chat_container = st.container(height=400)
        
        with chat_container:
            for msg in st.session_state.ai_chat_messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        # Chat input inside the popover
        if prompt := st.chat_input("Ask about this plot or data..."):
            # Append user message
            st.session_state.ai_chat_messages.append({"role": "user", "content": prompt})
            
            # Simple context awareness from session_state
            context_summary = []
            if "dashboard_scenario" in st.session_state:
                context_summary.append("Scenario loaded")
            if "dataset" in st.session_state:
                context_summary.append("Dataset active")
                
            ctx = ", ".join(context_summary) if context_summary else "No specific data loaded"
            
            # Mock AI response - in reality this would call the LLM Gateway
            response = (
                f"**Mock Analysis:** You asked '{prompt}'.\n\n"
                f"*Context:* {ctx}\n\n"
                "I will be connected to the LLM Gateway shortly to provide real scientific insights!"
            )
            
            st.session_state.ai_chat_messages.append({"role": "assistant", "content": response})
            st.rerun()
