"""Entry point of ``POST /assistant/ask`` (spec 08): the Work Assistant behind the API models.

The spec 08 router imports ``mentormind.agents.supervisor`` by this path; the work is in
``adapters.rest``.
"""

from mentormind.agents.adapters.rest import ask

__all__ = ["ask"]
