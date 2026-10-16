"""Concrete VLM providers. Each module registers itself with ``@register_vlm`` on import.

``openai_compat`` — every ``/chat/completions`` endpoint (self-hosted vLLM and cloud vendors);
``fake`` — scripted answers for tests and offline demos.
"""
