"""
Codex 配置文件生成器。
"""

import json
import os
import textwrap

from .proxy import PROXY_HOST, PROXY_PORT, DEFAULT_MODEL

CODEX_HOME = os.path.expanduser("~/.codex")
CONFIG_PATH = os.path.join(CODEX_HOME, "config.toml")
CATALOG_PATH = os.path.join(CODEX_HOME, "deepseek-models.json")


def make_config_toml(model=DEFAULT_MODEL):
    """生成 config.toml 内容"""
    return textwrap.dedent(f'''\
    personality = "pragmatic"
    model = "{model}"
    model_provider = "deepseek_proxy"
    model_context_window = 131072
    model_catalog_json = "{CATALOG_PATH}"

    [model_providers.deepseek_proxy]
    name = "DeepSeek (via proxy)"
    base_url = "http://{PROXY_HOST}:{PROXY_PORT}/v1"
    wire_api = "responses"
    supports_websockets = false
    env_key = "DEEPSEEK_API_KEY"
    ''')


def make_model_catalog(model=DEFAULT_MODEL):
    """生成模型元数据 JSON"""
    return {
        "models": [
            {
                "slug": model,
                "display_name": f"DeepSeek {model}",
                "description": "DeepSeek model via local proxy",
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 49,
                "context_window": 131072,
                "max_context_window": 131072,
                "supports_parallel_tool_calls": True,
                "apply_patch_tool_type": "freeform",
                "web_search_tool_type": "text_and_image",
                "input_modalities": ["text"],
                "truncation_policy": {"mode": "tokens", "limit": 10000},
                "supported_reasoning_levels": [],
                "additional_speed_tiers": [],
                "service_tiers": [],
                "availability_nux": None,
                "upgrade": None,
                "base_instructions": "",
                "model_messages": None,
                "supports_reasoning_summaries": False,
                "default_reasoning_summary": "none",
                "support_verbosity": False,
                "default_verbosity": "low",
                "supports_image_detail_original": False,
                "comp_hash": "deepseek",
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
                "supports_search_tool": False,
                "use_responses_lite": False,
            }
        ]
    }


def setup_all(model=DEFAULT_MODEL):
    """写入所有配置文件"""
    os.makedirs(CODEX_HOME, exist_ok=True)

    with open(CONFIG_PATH, "w") as f:
        f.write(make_config_toml(model))
    print(f"  ✓ {CONFIG_PATH}")

    with open(CATALOG_PATH, "w") as f:
        json.dump(make_model_catalog(model), f, indent=2)
    print(f"  ✓ {CATALOG_PATH}")
