"""Work Assistant and RCA Agent (spec 06).

``base/`` (``Agent``: the template method every agent runs through — LLM call + trace; tracing,
prompts, data labels), ``ports`` (what the agents need from spec 05/07, as Protocols), one package
per agent (``work_assistant/``, ``rca/``, each with its ``prompts/``), ``adapters/`` (factory
wiring the real components, ``GraphExperts``, the REST adapter), ``cli/`` (``knowhow agent``).
``supervisor.ask`` and ``rca.investigate`` are the entry points the spec 08 routers import.
"""
