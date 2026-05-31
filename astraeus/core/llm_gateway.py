import os
import logging
from typing import Optional

try:
    from dotenv import load_dotenv
    # Load environment variables from .env file if available
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

class LLMClient:
    """
    A unified gateway to interface with various Large Language Models (LLMs).
    Provides a standardized way to generate responses for explanations and reports.
    """
    def __init__(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = "You are an expert astrophysicist explaining transit data results."
    ):
        """
        Initializes the LLM Gateway.
        
        Args:
            provider (str): The LLM provider (e.g., 'openai', 'anthropic', 'google', 'ollama').
            api_key (str, optional): API key for the provider. If not provided, it will be loaded from environment variables.
            model_name (str, optional): Specific model to use. Defaults to the provider's standard model.
            system_prompt (str, optional): System prompt to ensure a consistent tone and role.
        """
        self.provider = provider.lower().strip()
        self.api_key = api_key or self._load_api_key()
        self.model_name = model_name or self._get_default_model()
        self.system_prompt = system_prompt
        
    def _load_api_key(self) -> Optional[str]:
        """Loads API key from environment variables based on the provider."""
        if self.provider == 'openai':
            return os.getenv("OPENAI_API_KEY")
        elif self.provider == 'anthropic':
            return os.getenv("ANTHROPIC_API_KEY")
        elif self.provider == 'google':
            return os.getenv("GOOGLE_API_KEY")
        elif self.provider == 'ollama':
            return None  # Local Ollama doesn't typically require an API key
        return None
        
    def _get_default_model(self) -> str:
        """Returns a sensible default model for each provider."""
        defaults = {
            'openai': 'gpt-4o',
            'anthropic': 'claude-3-opus-20240229',
            'google': 'gemini-1.5-pro-latest',
            'ollama': 'llama3'
        }
        return defaults.get(self.provider, 'unknown_model')

    def generate_response(self, prompt: str, context: Optional[str] = None) -> str:
        """
        Maps the standardized prompt and context to the specific API requirements of the chosen provider.
        
        Args:
            prompt (str): The specific question or task for the LLM.
            context (str, optional): Background data or text to inform the prompt.
            
        Returns:
            str: The LLM's generated response.
        """
        # Combine context and prompt if context is provided
        full_prompt = prompt
        if context:
            full_prompt = f"Context Data/Information:\n{context}\n\nTask/Question:\n{prompt}"
            
        if self.provider == 'openai':
            return self._call_openai(full_prompt)
        elif self.provider == 'anthropic':
            return self._call_anthropic(full_prompt)
        elif self.provider == 'google':
            return self._call_google(full_prompt)
        elif self.provider == 'ollama':
            return self._call_ollama(full_prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}. Choose from 'openai', 'anthropic', 'google', 'ollama'.")

    def _call_openai(self, prompt: str) -> str:
        try:
            import openai
        except ImportError:
            return "Error: 'openai' package is not installed. Run `pip install openai`."
            
        if not self.api_key:
            return "Error: OpenAI API key is missing."
            
        client = openai.OpenAI(api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return f"Error communicating with OpenAI: {e}"

    def _call_anthropic(self, prompt: str) -> str:
        try:
            import anthropic
        except ImportError:
            return "Error: 'anthropic' package is not installed. Run `pip install anthropic`."
            
        if not self.api_key:
            return "Error: Anthropic API key is missing."
            
        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            response = client.messages.create(
                model=self.model_name,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            return f"Error communicating with Anthropic: {e}"

    def _call_google(self, prompt: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            return "Error: 'google-generativeai' package is not installed. Run `pip install google-generativeai`."
            
        if not self.api_key:
            return "Error: Google API key is missing."
            
        genai.configure(api_key=self.api_key)
        try:
            # Using GenerativeModel with system_instruction support
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=self.system_prompt
            )
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Google Gemini error: {e}")
            return f"Error communicating with Google Gemini: {e}"

    def _call_ollama(self, prompt: str) -> str:
        try:
            import requests
        except ImportError:
            return "Error: 'requests' package is not installed. Run `pip install requests`."
            
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": self.system_prompt,
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama connection error: {e}")
            return f"Error communicating with local Ollama instance (make sure it's running): {e}"
