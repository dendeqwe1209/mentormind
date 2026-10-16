"""What every agent shares: ``Agent`` (template method ``run``: LLM call + trace), ``tracing``
(FR-04), ``prompting`` (each agent's ``prompts/``), ``context`` (data labels, fail closed)."""

from mentormind.agents.base.agent import Agent, AgentRun
from mentormind.agents.base.context import passage_label, row_label
from mentormind.agents.base.prompting import PromptBook
from mentormind.agents.base.tracing import TraceLog, TraceRecord, prompt_hash

__all__ = [
    "Agent",
    "AgentRun",
    "PromptBook",
    "TraceLog",
    "TraceRecord",
    "passage_label",
    "prompt_hash",
    "row_label",
]
