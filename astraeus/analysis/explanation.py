import json
import logging
from typing import Dict, Any

from astraeus.core.llm_gateway import LLMClient

logger = logging.getLogger(__name__)

def get_scientific_explanation(params: Dict[str, Any], uncertainties: Dict[str, Any], residuals: Dict[str, Any], provider: str = "google", model_name: str = None, api_key: str = None) -> Dict[str, str]:
    """
    Generates a scientific explanation of the MCMC retrieval results using an LLM.
    
    Args:
        params: Dictionary of fitted parameters.
        uncertainties: Dictionary of parameter uncertainties.
        residuals: Dictionary of residual statistics.
        
    Returns:
        Dictionary with three keys: physics_interpretation, parameter_breakdown, and uncertainty_analysis.
    """
    system_prompt = (
        "You are a senior astrophysicist. Explain these MCMC retrieval results focusing on "
        "parameter degeneracies, physical implications of the radius/inclination, and the "
        "reliability of the error bars."
    )
    
    client = LLMClient(provider=provider, model_name=model_name, api_key=api_key, system_prompt=system_prompt)
    
    context = (
        f"Fitted Parameters:\n{json.dumps(params, indent=2)}\n\n"
        f"Uncertainties:\n{json.dumps(uncertainties, indent=2)}\n\n"
        f"Residuals:\n{json.dumps(residuals, indent=2)}"
    )
    
    prompt = (
        "Analyze the provided MCMC results and generate the explanation.\n"
        "Return your response ONLY as a valid JSON object with exactly the following keys: "
        '"physics_interpretation", "parameter_breakdown", and "uncertainty_analysis". '
        "Do not include Markdown formatting like ```json in the output."
    )
    
    try:
        response_text = client.generate_response(prompt=prompt, context=context)
        
        # Clean up the text if it includes markdown code blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
            
        result = json.loads(clean_text.strip())
        
        return {
            "physics_interpretation": result.get("physics_interpretation", "No interpretation provided."),
            "parameter_breakdown": result.get("parameter_breakdown", "No parameter breakdown provided."),
            "uncertainty_analysis": result.get("uncertainty_analysis", "No uncertainty analysis provided.")
        }
    except Exception as e:
        logger.error(f"Error generating scientific explanation: {e}")
        return {
            "physics_interpretation": "Error generating interpretation.",
            "parameter_breakdown": "Error generating breakdown.",
            "uncertainty_analysis": f"Failed due to error: {str(e)}"
        }
