"""
Pipeline infrastructure configuration.

All sensitive values are read from environment variables (or .env file).
No API keys, URLs, or credentials are hardcoded here.

Copy .env.example to .env and fill in your values before running.
"""
import os

# Try to load .env file (optional dependency)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(_env_path)
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ═══════════════════════════════════════════════════════════════
# LLM — Model for structure-aware extraction
# ═══════════════════════════════════════════════════════════════

LLM_CONFIG = {
    "url": _env("LLM_URL"),
    "api_key": _env("LLM_API_KEY"),
    "model": _env("LLM_MODEL", "deepseek-v4-pro"),
    "temperature": float(_env("LLM_TEMPERATURE", "0.0")),
    "max_tokens": int(_env("LLM_MAX_TOKENS", "8192")),
    "timeout_seconds": int(_env("LLM_TIMEOUT", "180")),
    "max_retries": int(_env("LLM_MAX_RETRIES", "2")),
    "workers": int(_env("LLM_WORKERS", "5")),
}

# ═══════════════════════════════════════════════════════════════
# OCR_VL — Vision model for PDF -> Markdown
# ═══════════════════════════════════════════════════════════════

OCR_CONFIG = {
    "api_url": _env("OCR_URL"),
    "prompt": _env("OCR_PROMPT"),
    "dpi": int(_env("OCR_DPI", "200")),
    "timeout_seconds": int(_env("OCR_TIMEOUT", "300")),
    "batch": {
        "workers": int(_env("OCR_BATCH_WORKERS", "5")),
        "input_dir": _env("OCR_BATCH_INPUT_DIR"),
        "output_dir": _env("OCR_BATCH_OUTPUT_DIR"),
    },
}

# ═══════════════════════════════════════════════════════════════
# ODL — opendataloader for GFM reference
# ═══════════════════════════════════════════════════════════════

ODL_CONFIG = {
    "package": "opendataloader-pdf",
    "import": "opendataloader",
    "function": "convert_pdf",
}

# ═══════════════════════════════════════════════════════════════
# MinerU — Cloud PDF -> Markdown (async batch-job API)
# ═══════════════════════════════════════════════════════════════

MINERU_CONFIG = {
    "token": _env("MINERU_TOKEN"),
    "url": _env("MINERU_URL", "https://mineru.net/api/v4"),
    "model_version": _env("MINERU_MODEL_VERSION", "vlm"),
    "language": _env("MINERU_LANGUAGE", "ch"),
    "enable_table": _env("MINERU_ENABLE_TABLE", "true").lower() == "true",
    "poll_interval_seconds": int(_env("MINERU_POLL_INTERVAL", "10")),
    "poll_max_seconds": int(_env("MINERU_POLL_MAX", "600")),
    "batch": {
        "workers": int(_env("MINERU_BATCH_WORKERS", "3")),
        "input_dir": _env("MINERU_BATCH_INPUT_DIR"),
        "output_dir": _env("MINERU_BATCH_OUTPUT_DIR"),
    },
}

# ═══════════════════════════════════════════════════════════════
# Converter selection — "ocr_vl" (default) or "mineru"
# ═══════════════════════════════════════════════════════════════

CONVERTER = _env("CONVERTER", "ocr_vl")
