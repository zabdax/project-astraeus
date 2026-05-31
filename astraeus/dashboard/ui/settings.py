"""Settings panel module for configuring global application state."""

import streamlit as st
from astraeus.core.config import load_config

def initialize_settings():
    """Load config.json and initialize session_state if not already done."""
    if "settings_initialized" not in st.session_state:
        config = load_config()
        st.session_state["llm_provider"] = config.get("llm_provider", "google")
        st.session_state["llm_model"] = config.get("llm_model", "gemini-1.5-pro-latest")
        
        # Load API keys from config if available
        api_keys = config.get("api_keys", {})
        # Note: If there are existing env variables or session states, you might want to preserve them.
        st.session_state["llm_api_key"] = api_keys.get(st.session_state["llm_provider"], "")
        
        st.session_state["settings_initialized"] = True

def render_settings_panel() -> None:
    """Render the global settings panel for API keys and model choices."""
    st.title("System Settings")
    st.markdown("Configure global parameters, API keys, and model preferences. These settings persist across your session.")
    
    # Initialize settings if needed
    initialize_settings()
    
    st.subheader("Model Selection")
    
    provider_options = ["google", "openai", "anthropic", "ollama"]
    current_provider = st.session_state.get("llm_provider", "google")
    provider_idx = provider_options.index(current_provider) if current_provider in provider_options else 0
    
    # Update session state on change
    selected_provider = st.selectbox(
        "Provider",
        provider_options,
        index=provider_idx,
    )
    if selected_provider != current_provider:
        st.session_state["llm_provider"] = selected_provider
        # Clear or load specific API key for the newly selected provider here if desired
        st.rerun()
    
    st.session_state["llm_model"] = st.text_input(
        "Model Name",
        value=st.session_state.get("llm_model", "gemini-1.5-pro-latest"),
    )
    
    st.subheader("API Configuration")
    st.session_state["llm_api_key"] = st.text_input(
        f"{st.session_state['llm_provider'].capitalize()} API Key",
        value=st.session_state.get("llm_api_key", ""),
        type="password"
    )
    
    st.markdown("---")
    st.info("Settings are automatically saved to your current session state. To persist them permanently, update `config.json`.")
