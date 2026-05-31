"""Synthesis layer: the model is one component, not the system.

This package may touch the network (Ollama) — unlike verify/, which may not.
"""

from myAIstory.synth.base import LLM
from myAIstory.synth.client import OllamaClient, OllamaError
from myAIstory.synth.drafts import stream_collect
from myAIstory.synth.jsonio import JSONExtractError, extract_json
from myAIstory.synth.scripted import ScriptedLLM

__all__ = [
    "LLM",
    "OllamaClient",
    "OllamaError",
    "ScriptedLLM",
    "JSONExtractError",
    "extract_json",
    "stream_collect",
]
