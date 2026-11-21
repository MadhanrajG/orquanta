# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta Model Registry — Phase 3B
=====================================
Model discovery, metadata, Hugging Face integration, licence validation.

SECURITY:
- Never automatically execute untrusted model code.
- Licence permissions are reported as-known; unknown licences flagged explicitly.
- HF token (read-only) is used only for public metadata fetching.
- Model checksums verified where available.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("orquanta.inference.registry")

HF_TOKEN = os.getenv("HF_TOKEN", "")           # Read-only HF token for metadata
HF_API_BASE = "https://huggingface.co/api"

# ---------------------------------------------------------------------------
# Licence database
# ---------------------------------------------------------------------------

# Maps SPDX / HF licence identifiers to usage permissions
# Sources: SPDX (https://spdx.org/licenses), HF licence cards
_LICENCE_DB: Dict[str, Dict[str, Any]] = {
    "mit":              {"spdx": "MIT",            "commercial": True,  "redistribution": True,  "known": True},
    "apache-2.0":       {"spdx": "Apache-2.0",     "commercial": True,  "redistribution": True,  "known": True},
    "llama2":           {"spdx": "LLaMA 2 CLA",    "commercial": True,  "redistribution": False, "known": True,
                         "note": "Commercial use allowed for <700M MAU; attribution required."},
    "llama3":           {"spdx": "Meta LLaMA 3",   "commercial": True,  "redistribution": False, "known": True,
                         "note": "Same as LLaMA 2 CLA with updated terms."},
    "gemma":            {"spdx": "Gemma",           "commercial": True,  "redistribution": False, "known": True,
                         "note": "Prohibited uses: harmful content, impersonation."},
    "mistral":          {"spdx": "Apache-2.0",     "commercial": True,  "redistribution": True,  "known": True},
    "deepseek":         {"spdx": "DeepSeek",        "commercial": True,  "redistribution": False, "known": True,
                         "note": "Commercial use allowed; no misuse for harmful activities."},
    "cc-by-4.0":        {"spdx": "CC-BY-4.0",      "commercial": True,  "redistribution": True,  "known": True},
    "cc-by-nc-4.0":     {"spdx": "CC-BY-NC-4.0",   "commercial": False, "redistribution": True,  "known": True,
                         "note": "Non-commercial use only."},
    "cc-by-nc-sa-4.0":  {"spdx": "CC-BY-NC-SA-4.0","commercial": False, "redistribution": True,  "known": True,
                         "note": "Non-commercial, ShareAlike."},
    "gpl-3.0":          {"spdx": "GPL-3.0",        "commercial": True,  "redistribution": True,  "known": True,
                         "note": "Copyleft — derivatives must be GPL-3.0."},
    "openrail":         {"spdx": "OpenRAIL",        "commercial": True,  "redistribution": True,  "known": True,
                         "note": "Responsible AI licence — prohibits harmful uses."},
    "openrail++":       {"spdx": "OpenRAIL++",      "commercial": True,  "redistribution": True,  "known": True,
                         "note": "Enhanced OpenRAIL with additional use restrictions."},
    "bigscience-bloom-rail-1.0": {"spdx": "BLOOM-RAIL", "commercial": False, "redistribution": False, "known": True,
                         "note": "Non-commercial research only."},
    "other":            {"spdx": "Other",           "commercial": None,  "redistribution": None,  "known": False,
                         "note": "Licence terms unknown — review model card before commercial use."},
}


def get_licence_info(licence_id: str) -> Dict[str, Any]:
    """Return licence permissions. If unknown, marks commercial as None and known=False."""
    if not licence_id:
        return _LICENCE_DB["other"]
    return _LICENCE_DB.get(licence_id.lower(), {
        **_LICENCE_DB["other"],
        "spdx": licence_id,
        "note": f"Licence '{licence_id}' is not in OrQuanta's licence database — review the model card.",
    })


# ---------------------------------------------------------------------------
# Model record
# ---------------------------------------------------------------------------

@dataclass
class ModelRecord:
    """Full model metadata record."""
    model_id: str                              # OrQuanta canonical ID, e.g. "meta-llama/Llama-3.1-70B-Instruct"
    hf_id: str                                 # Hugging Face repo ID
    name: str                                  # Display name
    publisher: str                             # Organisation
    description: str = ""
    model_family: str = ""                     # llama, mistral, gemma, qwen, …
    revision: str = "main"                     # Git revision / commit SHA
    licence: str = "other"
    licence_info: Dict[str, Any] = field(default_factory=dict)
    commercial_ok: Optional[bool] = None
    supported_engines: List[str] = field(default_factory=list)   # vllm, sglang, transformers
    context_length: Optional[int] = None
    param_count: Optional[str] = None          # "70B", "8B", "405B"
    quant_options: List[str] = field(default_factory=list)       # ["fp16", "int8", "int4", "gptq", "awq"]
    vram_fp16_gb: Optional[float] = None       # Estimated VRAM for FP16 (rule of thumb: 2 × params in GB)
    vram_int8_gb: Optional[float] = None
    vram_int4_gb: Optional[float] = None
    gpu_min: str = ""                          # Human-readable minimum GPU, e.g. "1×A10 24GB"
    tags: List[str] = field(default_factory=list)
    hf_downloads: int = 0
    hf_likes: int = 0
    trending: bool = False
    deployment_status: str = "available"       # available | deployed | unavailable
    benchmark_results: Dict[str, Any] = field(default_factory=dict)
    provenance_verified: bool = False
    checksum: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Built-in curated registry
# ---------------------------------------------------------------------------
# Curated entries serve as the offline fallback when HF API is unavailable.
# Data sourced from public model cards, HF model pages, and published benchmarks.

_CURATED_MODELS: List[ModelRecord] = [
    ModelRecord(
        model_id="meta-llama/Llama-3.1-405B-Instruct",
        hf_id="meta-llama/Llama-3.1-405B-Instruct",
        name="LLaMA 3.1 405B Instruct",
        publisher="Meta AI",
        description="Largest open-weight LLM from Meta. Exceptional reasoning, multilingual, 128K context. Matches GPT-4 class on most benchmarks.",
        model_family="llama",
        licence="llama3",
        supported_engines=["vllm", "sglang", "transformers"],
        context_length=131072,
        param_count="405B",
        quant_options=["fp16", "int8", "int4", "awq"],
        vram_fp16_gb=810.0,
        vram_int8_gb=405.0,
        vram_int4_gb=203.0,
        gpu_min="8×H100 80GB",
        tags=["Flagship", "128K Context", "Multilingual", "RLHF"],
        trending=True,
    ),
    ModelRecord(
        model_id="meta-llama/Llama-3.1-70B-Instruct",
        hf_id="meta-llama/Llama-3.1-70B-Instruct",
        name="LLaMA 3.1 70B Instruct",
        publisher="Meta AI",
        description="Best cost-performance for production LLM workloads. 128K context, strong code and reasoning.",
        model_family="llama",
        licence="llama3",
        supported_engines=["vllm", "sglang", "transformers"],
        context_length=131072,
        param_count="70B",
        quant_options=["fp16", "int8", "int4", "awq", "gptq"],
        vram_fp16_gb=140.0,
        vram_int8_gb=70.0,
        vram_int4_gb=35.0,
        gpu_min="2×A100 80GB",
        tags=["Production", "128K Context", "Fine-tunable"],
        trending=True,
    ),
    ModelRecord(
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        hf_id="meta-llama/Llama-3.1-8B-Instruct",
        name="LLaMA 3.1 8B Instruct",
        publisher="Meta AI",
        description="Lightweight yet powerful. Ideal for fine-tuning, edge deployment, and budget-conscious inference.",
        model_family="llama",
        licence="llama3",
        supported_engines=["vllm", "sglang", "transformers"],
        context_length=131072,
        param_count="8B",
        quant_options=["fp16", "int8", "int4", "gguf", "awq", "gptq"],
        vram_fp16_gb=16.0,
        vram_int8_gb=8.0,
        vram_int4_gb=4.5,
        gpu_min="1×A10 24GB",
        tags=["Lightweight", "Fine-tunable", "Edge"],
    ),
    ModelRecord(
        model_id="deepseek-ai/DeepSeek-V3",
        hf_id="deepseek-ai/DeepSeek-V3",
        name="DeepSeek-V3",
        publisher="DeepSeek AI",
        description="State-of-the-art 671B MoE. Outperforms GPT-4o on coding and math. 128K context with efficient sparse activation.",
        model_family="deepseek",
        licence="deepseek",
        supported_engines=["vllm", "transformers"],
        context_length=131072,
        param_count="671B MoE",
        quant_options=["fp16", "int8", "int4", "awq"],
        vram_fp16_gb=380.0,  # MoE: active params ~37B, full weights ~671B
        vram_int8_gb=190.0,
        vram_int4_gb=95.0,
        gpu_min="8×H100 80GB",
        tags=["MoE", "SOTA", "MIT-like", "128K Context"],
        trending=True,
    ),
    ModelRecord(
        model_id="deepseek-ai/DeepSeek-R1",
        hf_id="deepseek-ai/DeepSeek-R1",
        name="DeepSeek-R1",
        publisher="DeepSeek AI",
        description="Chain-of-thought reasoning model. Matches o1-preview on math and code reasoning. MIT licence.",
        model_family="deepseek",
        licence="mit",
        supported_engines=["vllm", "transformers"],
        context_length=131072,
        param_count="671B MoE",
        quant_options=["fp16", "int8", "int4"],
        vram_fp16_gb=380.0,
        vram_int8_gb=190.0,
        vram_int4_gb=95.0,
        gpu_min="8×H100 80GB",
        tags=["Reasoning", "MIT License", "CoT", "SOTA"],
        trending=True,
    ),
    ModelRecord(
        model_id="Qwen/Qwen2.5-72B-Instruct",
        hf_id="Qwen/Qwen2.5-72B-Instruct",
        name="Qwen 2.5 72B Instruct",
        publisher="Alibaba Cloud",
        description="Multilingual instruction-tuned model. Excellent on coding, math, and long-document understanding.",
        model_family="qwen",
        licence="apache-2.0",
        supported_engines=["vllm", "sglang", "transformers"],
        context_length=131072,
        param_count="72B",
        quant_options=["fp16", "int8", "int4", "awq", "gptq"],
        vram_fp16_gb=144.0,
        vram_int8_gb=72.0,
        vram_int4_gb=36.0,
        gpu_min="2×A100 80GB",
        tags=["Apache-2.0", "Multilingual", "Long Context"],
    ),
    ModelRecord(
        model_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        hf_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        name="Mixtral 8×7B Instruct",
        publisher="Mistral AI",
        description="Sparse MoE model. 2 of 8 experts active per token. Strong performance at efficient inference cost.",
        model_family="mistral",
        licence="apache-2.0",
        supported_engines=["vllm", "sglang", "transformers"],
        context_length=32768,
        param_count="46.7B (8×7B MoE)",
        quant_options=["fp16", "int8", "int4", "awq", "gptq", "gguf"],
        vram_fp16_gb=94.0,
        vram_int8_gb=47.0,
        vram_int4_gb=24.0,
        gpu_min="2×A100 40GB",
        tags=["MoE", "Apache-2.0", "32K Context"],
    ),
    ModelRecord(
        model_id="google/gemma-2-27b-it",
        hf_id="google/gemma-2-27b-it",
        name="Gemma 2 27B IT",
        publisher="Google",
        description="Google's efficient 27B model. Outperforms models twice its size on many benchmarks.",
        model_family="gemma",
        licence="gemma",
        supported_engines=["vllm", "transformers"],
        context_length=8192,
        param_count="27B",
        quant_options=["fp16", "int8", "int4"],
        vram_fp16_gb=54.0,
        vram_int8_gb=27.0,
        vram_int4_gb=14.0,
        gpu_min="1×A100 80GB",
        tags=["Efficient", "Instruction-tuned"],
    ),
    ModelRecord(
        model_id="microsoft/phi-4",
        hf_id="microsoft/phi-4",
        name="Phi-4",
        publisher="Microsoft Research",
        description="14B parameter model that outperforms much larger models on reasoning and STEM benchmarks.",
        model_family="phi",
        licence="mit",
        supported_engines=["vllm", "transformers"],
        context_length=16384,
        param_count="14B",
        quant_options=["fp16", "int8", "int4", "gguf"],
        vram_fp16_gb=28.0,
        vram_int8_gb=14.0,
        vram_int4_gb=7.5,
        gpu_min="1×A10 24GB",
        tags=["MIT License", "Efficient", "STEM", "Reasoning"],
        trending=True,
    ),
    # Embedding models
    ModelRecord(
        model_id="BAAI/bge-m3",
        hf_id="BAAI/bge-m3",
        name="BGE-M3",
        publisher="BAAI",
        description="State-of-the-art multilingual embedding model. Supports dense, sparse, and multi-vector retrieval.",
        model_family="bge",
        licence="mit",
        supported_engines=["vllm", "transformers"],
        context_length=8192,
        param_count="568M",
        quant_options=["fp16", "int8"],
        vram_fp16_gb=1.2,
        vram_int8_gb=0.6,
        gpu_min="1×T4 16GB",
        tags=["Embeddings", "MIT License", "Multilingual"],
    ),
]

# Fast lookup dict
_REGISTRY: Dict[str, ModelRecord] = {m.model_id: m for m in _CURATED_MODELS}


def list_models(
    family: Optional[str] = None,
    licence_commercial_ok: Optional[bool] = None,
    engine: Optional[str] = None,
    search: Optional[str] = None,
) -> List[ModelRecord]:
    """List models with optional filters."""
    results = list(_REGISTRY.values())
    if family:
        results = [m for m in results if m.model_family == family.lower()]
    if licence_commercial_ok is not None:
        results = [m for m in results if m.licence_info.get("commercial") == licence_commercial_ok
                   or get_licence_info(m.licence).get("commercial") == licence_commercial_ok]
    if engine:
        results = [m for m in results if engine in m.supported_engines]
    if search:
        q = search.lower()
        results = [m for m in results
                   if q in m.name.lower() or q in m.description.lower()
                   or q in m.publisher.lower() or q in " ".join(m.tags).lower()]
    return results


def get_model(model_id: str) -> Optional[ModelRecord]:
    """Return model record by ID."""
    return _REGISTRY.get(model_id)


def register_model(record: ModelRecord) -> None:
    """Register a model in the in-process registry."""
    record.licence_info = get_licence_info(record.licence)
    record.commercial_ok = record.licence_info.get("commercial")
    _REGISTRY[record.model_id] = record
    logger.info("[registry] registered model=%s", record.model_id)


# Populate licence_info at module load
for _m in _CURATED_MODELS:
    _m.licence_info = get_licence_info(_m.licence)
    _m.commercial_ok = _m.licence_info.get("commercial")


# ---------------------------------------------------------------------------
# Hugging Face metadata fetcher
# ---------------------------------------------------------------------------

async def fetch_hf_metadata(hf_model_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch public metadata from the Hugging Face Hub API.

    Args:
        hf_model_id: Hugging Face repository ID, e.g. 'meta-llama/Llama-3.1-8B-Instruct'

    Returns:
        Dict with model card metadata, or None on failure.

    Notes:
        - Uses read-only HF_TOKEN if set.
        - Does NOT download weights or execute model code.
        - Only fetches public metadata fields.
    """
    headers: Dict[str, str] = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    url = f"{HF_API_BASE}/models/{hf_model_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("[registry] HF API HTTP %d for %s", e.response.status_code, hf_model_id)
        return None
    except Exception as e:
        logger.warning("[registry] HF API error for %s: %s", hf_model_id, e)
        return None

    # Extract safe fields from model card
    card_data = data.get("cardData", {}) or {}
    return {
        "hf_id": data.get("id", hf_model_id),
        "name": data.get("id", hf_model_id).split("/")[-1].replace("-", " ").replace("_", " "),
        "publisher": (data.get("id", "/").split("/")[0]),
        "description": card_data.get("model-index", [{}])[0].get("name", "") if card_data.get("model-index") else "",
        "licence": data.get("license", "other"),
        "tags": data.get("tags", []),
        "hf_downloads": data.get("downloads", 0),
        "hf_likes": data.get("likes", 0),
        "revision": data.get("sha", "main"),
        "context_length": _extract_context_length(data),
        "param_count": _extract_param_count(data),
        "created_at": data.get("createdAt"),
    }


def _extract_context_length(data: Dict) -> Optional[int]:
    """Try to extract context length from model card metadata."""
    config = data.get("config", {}) or {}
    for key in ("max_position_embeddings", "n_positions", "max_seq_len", "seq_length"):
        v = config.get(key)
        if isinstance(v, int):
            return v
    return None


def _extract_param_count(data: Dict) -> Optional[str]:
    """Extract parameter count string from tags or safetensors metadata."""
    tags = data.get("tags", [])
    for tag in tags:
        for suffix in ("b", "B", "m", "M"):
            if tag.endswith(suffix) and tag[:-1].replace(".", "").isdigit():
                return tag.upper()
    # From safetensors_info total_size (bytes → params assuming fp16)
    st = data.get("safetensors", {})
    if st and "total" in st:
        total_bytes = st["total"]
        params = total_bytes // 2  # fp16 = 2 bytes/param
        if params > 1_000_000_000:
            return f"{params / 1e9:.0f}B"
        elif params > 1_000_000:
            return f"{params / 1e6:.0f}M"
    return None


async def search_hf_models(
    query: str,
    limit: int = 20,
    sort: str = "downloads",
) -> List[Dict[str, Any]]:
    """
    Search the HF Hub for models matching a query.

    Returns list of partial metadata dicts (not full ModelRecord).
    """
    headers: Dict[str, str] = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    params = {
        "search": query,
        "sort": sort,
        "limit": min(limit, 50),
        "full": "false",
        "config": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{HF_API_BASE}/models", params=params, headers=headers)
            resp.raise_for_status()
            models = resp.json()
    except Exception as e:
        logger.warning("[registry] HF search error: %s", e)
        return []

    return [
        {
            "hf_id": m.get("id", ""),
            "name": m.get("id", "").split("/")[-1],
            "publisher": m.get("id", "/").split("/")[0],
            "licence": m.get("license", "other"),
            "licence_info": get_licence_info(m.get("license", "other")),
            "tags": m.get("tags", []),
            "hf_downloads": m.get("downloads", 0),
            "hf_likes": m.get("likes", 0),
            "in_registry": m.get("id", "") in _REGISTRY,
        }
        for m in models
    ]
