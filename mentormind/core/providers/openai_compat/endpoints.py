"""OpenAI-compatible endpoints: one table of vendor facts, shared by every provider kind.

Every vendor that speaks ``POST {base_url}/chat/completions`` is a ROW here, not a class. Adding a
vendor = one row + its name in the kind's ``@register_*`` list (see ``.secrets/README.md`` for how
its key is looked up). ``openai_compatible`` is deliberately absent: it means "some server you
name", so it has no base URL to guess and its cloud flag is derived from the URL you give it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from mentormind.core.config import JsonMode

#: Registry name of the generic "any OpenAI-compatible server" provider.
GENERIC_OPENAI_COMPATIBLE = "openai_compatible"
#: Registry name of the self-hosted server in ``3rdparty/vlm_server`` (spec 04 FR-08): Ollama.
LOCAL_OPENAI = "local_openai"
LOCAL_VLM_BASE_URL = "http://127.0.0.1:11434/v1"


class Endpoint(BaseModel):
    """How to reach one OpenAI-compatible vendor."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    #: Calls leave the premises (DataGuard blocks factory_confidential data).
    is_cloud: bool
    #: Secret variable holding the key; None = the endpoint needs no key.
    api_key_env: str | None
    #: Secret variable that may override ``base_url`` (per-account hosts, e.g. DashScope).
    base_url_env: str | None = None
    #: What ``json_mode="auto"`` resolves to: the strongest ``response_format`` it honours.
    json_mode: JsonMode
    #: Where a human gets a key / reads pricing (shown by ``knowhow vlm providers``).
    console_url: str


OPENAI_COMPAT_ENDPOINTS: dict[str, Endpoint] = {
    LOCAL_OPENAI: Endpoint(
        base_url=LOCAL_VLM_BASE_URL,
        is_cloud=False,
        api_key_env="VLM_SERVER_API_KEY",
        json_mode="json_schema",
        console_url="3rdparty/vlm_server/scripts/README.md",
    ),
    # Alibaba Model Studio (DashScope), Singapore. Retires qwen3-vl-8b-instruct on 2026-10-10.
    # New Singapore keys (sk-ws...) come with a workspace host shown next to the key. Put
    #   https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1
    # in DASHSCOPE_BASE_URL (.env); this legacy URL is only the fallback.
    "qwen_api": Endpoint(
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        is_cloud=True,
        api_key_env="DASHSCOPE_API_KEY",
        base_url_env="DASHSCOPE_BASE_URL",
        json_mode="json_object",
        console_url="https://modelstudio.console.alibabacloud.com/",
    ),
    # Upstreams for Qwen3-VL-8B (checked 2026-09-28): Alibaba and Parasail, both honour
    # structured outputs.
    "openrouter": Endpoint(
        base_url="https://openrouter.ai/api/v1",
        is_cloud=True,
        api_key_env="OPENROUTER_API_KEY",
        json_mode="json_schema",
        console_url="https://openrouter.ai/settings/keys",
    ),
    # International site (not siliconflow.cn, which needs a +86 phone). JSON mode, no schema.
    "siliconflow": Endpoint(
        base_url="https://api.siliconflow.com/v1",
        is_cloud=True,
        api_key_env="SILICONFLOW_API_KEY",
        json_mode="json_object",
        console_url="https://cloud.siliconflow.com/account/ak",
    ),
}
