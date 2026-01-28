from __future__ import annotations

import os
from typing import Optional, Tuple

import requests

API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")
DEFAULT_SYSTEM_PROMPT = (
    "You are a concise writing partner that helps researchers document lab work. "
    "Clean up the text, keep it factual, and highlight measurable outcomes."
)


def _load_key(explicit_key: Optional[str] = None) -> Optional[str]:
    if explicit_key:
        return explicit_key
    env_key = os.getenv("GROQ_API_KEY")
    if env_key:
        return env_key
    try:
        import streamlit as st  # type: ignore

        secrets = st.secrets
        if "GROQ_API_KEY" in secrets:
            return secrets["GROQ_API_KEY"]
        if "groq" in secrets and "api_key" in secrets["groq"]:
            return secrets["groq"]["api_key"]
    except Exception:
        pass
    return None


def request_completion(
    prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 400,
    api_key: Optional[str] = None,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Send a chat completion request to Groq's OpenAI-compatible endpoint."""
    key = _load_key(api_key)
    if not key:
        return None, "Set GROQ_API_KEY in .streamlit/secrets.toml or as an environment variable."

    payload = {
        "model": model or DEFAULT_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt.strip()},
        ],
    }

    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        return None, f"Groq request failed: {exc}"

    if response.status_code >= 400:
        return None, f"Groq API error {response.status_code}: {response.text}"

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content, None
    except (KeyError, IndexError, TypeError):
        return None, "Unexpected response from Groq API."


def polish_text(text: str, intent: str) -> Tuple[Optional[str], Optional[str]]:
    """Convenience helper used by the Streamlit UI."""
    prompt = (
        "Rewrite the following note so it clearly communicates "
        f"{intent}. Keep technical terminology, reply in less than 180 words.\n\n"
        f"TEXT:\n{text.strip()}"
    )
    return request_completion(prompt)
