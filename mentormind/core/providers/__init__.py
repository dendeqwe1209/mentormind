"""Every model provider: the parts all kinds share, then one sub-package per kind.

Shared: ``base``/``models`` (interface, config, usage), ``registry`` (name -> class), ``errors``,
``transport`` (HTTP + retry), ``openai_compat`` (vendor endpoints, locality), ``parsing`` (JSON).
Kinds: ``vlm`` (frames + prompt, spec 04), ``llm`` (text, spec 06) and ``asr`` (speech-to-text, spec 03).
Business code only calls a kind's factory (``get_vlm_provider``, ``get_llm_provider``,
``get_asr_provider``); it never subclasses a provider.
"""
