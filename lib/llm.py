"""LLM integration – Google Gemini."""

import logging
import os

import google.generativeai as genai

from lib.auth import ApiError

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)


def call_llm(prompt, model="gemini-1.5-flash", temperature=0.7, max_tokens=4000):
    """Send a prompt to the configured LLM and return the text response."""
    if not prompt:
        raise ApiError("Prompt is required for LLM call")

    try:
        if model.startswith("gemini") and GEMINI_KEY:
            model_obj = genai.GenerativeModel(
                model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            response = model_obj.generate_content(prompt)
            return response.text
        raise ApiError("No LLM model configured. Please set GEMINI_KEY.")
    except ApiError:
        raise
    except Exception as exc:
        logger.exception("LLM call failed")
        raise ApiError(f"LLM error: {exc}", 500) from exc
