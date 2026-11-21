# Copyright 2026 OrQuanta — Apache License 2.0
"""
OrQuanta GPU Compatibility Engine — Phase 3C
==============================================
Evaluates whether a model can run on a given GPU configuration.

Output:
  compatible              — model fits and should perform well
  compatible_with_constraints — model fits with quantisation or batch-size caveats
  incompatible            — model cannot fit
  insufficient_information — required parameters missing

NEVER guarantee performance based on theoretical VRAM estimates alone.
Real throughput depends on driver versions, CUDA kernels, attention implementation,
batch size, sequence length, and concurrent load.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orquanta.inference.gpu_compat")

# ---------------------------------------------------------------------------
# GPU hardware database
# ---------------------------------------------------------------------------
# VRAM values are from NVIDIA official specifications.
# TFLOPs are FP16 (Tensor Core) unless noted.

GPU_DB: Dict[str, Dict[str, Any]] = {
    # Data-centre
    "h100-sxm":    {"vram_gb": 80,  "tflops_fp16": 989.4, "arch": "Hopper",  "gen": "sm_90"},
    "h100-pcie":   {"vram_gb": 80,  "tflops_fp16": 756.0, "arch": "Hopper",  "gen": "sm_90"},
    "a100-80gb":   {"vram_gb": 80,  "tflops_fp16": 312.0, "arch": "Ampere",  "gen": "sm_80"},
    "a100-40gb":   {"vram_gb": 40,  "tflops_fp16": 312.0, "arch": "Ampere",  "gen": "sm_80"},
    "a40":         {"vram_gb": 48,  "tflops_fp16": 149.7, "arch": "Ampere",  "gen": "sm_86"},
    "a30":         {"vram_gb": 24,  "tflops_fp16": 165.0, "arch": "Ampere",  "gen": "sm_80"},
    "a10":         {"vram_gb": 24,  "tflops_fp16": 125.0, "arch": "Ampere",  "gen": "sm_86"},
    "a10g":        {"vram_gb": 24,  "tflops_fp16": 125.0, "arch": "Ampere",  "gen": "sm_86"},
    "l40":         {"vram_gb": 48,  "tflops_fp16": 362.0, "arch": "Ada",     "gen": "sm_89"},
    "l40s":        {"vram_gb": 48,  "tflops_fp16": 733.0, "arch": "Ada",     "gen": "sm_89"},
    "l4":          {"vram_gb": 24,  "tflops_fp16": 242.0, "arch": "Ada",     "gen": "sm_89"},
    # Consumer/workstation
    "rtx-4090":    {"vram_gb": 24,  "tflops_fp16": 330.3, "arch": "Ada",     "gen": "sm_89"},
    "rtx-3090":    {"vram_gb": 24,  "tflops_fp16": 142.6, "arch": "Ampere",  "gen": "sm_86"},
    "rtx-3090-ti": {"vram_gb": 24,  "tflops_fp16": 160.0, "arch": "Ampere",  "gen": "sm_86"},
    "rtx-4080":    {"vram_gb": 16,  "tflops_fp16": 242.0, "arch": "Ada",     "gen": "sm_89"},
    "rtx-3080":    {"vram_gb": 10,  "tflops_fp16": 119.6, "arch": "Ampere",  "gen": "sm_86"},
    # Cloud-common
    "t4":          {"vram_gb": 16,  "tflops_fp16":  65.1, "arch": "Turing",  "gen": "sm_75"},
    "v100-32gb":   {"vram_gb": 32,  "tflops_fp16": 125.0, "arch": "Volta",   "gen": "sm_70"},
    "v100-16gb":   {"vram_gb": 16,  "tflops_fp16": 125.0, "arch": "Volta",   "gen": "sm_70"},
    "p100":        {"vram_gb": 16,  "tflops_fp16":  18.7, "arch": "Pascal",  "gen": "sm_60"},
}

# ---------------------------------------------------------------------------
# Quantisation VRAM overhead multipliers (relative to FP16)
# These are approximate; actual depends on framework and kernel implementation.
# ---------------------------------------------------------------------------
QUANT_VRAM_FACTOR: Dict[str, float] = {
    "fp32":  2.0,
    "bf16":  1.0,
    "fp16":  1.0,
    "int8":  0.52,   # ~half + activations
    "int4":  0.28,   # ~quarter + activations + overhead
    "gptq":  0.30,
    "awq":   0.28,
    "gguf":  0.30,
}

# KV-cache VRAM estimate: approximately 0.125 × batch × seq_len × layers × heads × head_dim bytes
# Simplified: add 15% overhead for KV cache at batch=1, 2048 tokens
KV_CACHE_OVERHEAD = 0.15

# ---------------------------------------------------------------------------
# Engine-to-architecture compatibility
# ---------------------------------------------------------------------------
ENGINE_MIN_ARCH: Dict[str, int] = {
    "vllm":         70,   # sm_70 (Volta) minimum
    "sglang":       80,   # sm_80 (Ampere) minimum
    "transformers": 60,   # sm_60 (Pascal) minimum
    "llamacpp":     60,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CompatibilityResult:
    status: str                                 # compatible | compatible_with_constraints | incompatible | insufficient_information
    gpu_model: str
    gpu_count: int
    model_id: str
    quantisation: str
    engine: str
    total_vram_available_gb: float
    estimated_vram_required_gb: float
    headroom_gb: float
    constraints: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    estimated_tokens_per_second: Optional[float] = None
    estimated_cost_per_1m_tokens_usd: Optional[float] = None
    gpu_arch: str = ""
    gpu_gen: str = ""


def check_compatibility(
    model_id: str,
    gpu_model: str,
    gpu_count: int,
    quantisation: str,
    engine: str,
    context_length: Optional[int] = None,
    vram_fp16_gb: Optional[float] = None,       # Override — from registry or user-supplied
    param_count_str: Optional[str] = None,
) -> CompatibilityResult:
    """
    Evaluate whether a model fits on a GPU configuration.

    Args:
        model_id: OrQuanta model identifier (for context)
        gpu_model: GPU model key from GPU_DB, e.g. 'a100-80gb'
        gpu_count: Number of GPUs (for multi-GPU setups)
        quantisation: Quantisation type, e.g. 'fp16', 'int8', 'int4'
        engine: Inference engine, e.g. 'vllm', 'sglang', 'transformers'
        context_length: Requested context length in tokens
        vram_fp16_gb: Override for FP16 VRAM requirement (from model registry)
        param_count_str: Override parameter count string, e.g. '70B'

    Returns:
        CompatibilityResult with status and detailed reasons.
    """
    gpu_key = gpu_model.lower().replace(" ", "-")
    gpu_info = GPU_DB.get(gpu_key)

    if not gpu_info:
        return CompatibilityResult(
            status="insufficient_information",
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            model_id=model_id,
            quantisation=quantisation,
            engine=engine,
            total_vram_available_gb=0.0,
            estimated_vram_required_gb=0.0,
            headroom_gb=0.0,
            reasons=[f"GPU '{gpu_model}' is not in OrQuanta's hardware database. Submit a compatible GPU from the known list."],
        )

    if not vram_fp16_gb:
        return CompatibilityResult(
            status="insufficient_information",
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            model_id=model_id,
            quantisation=quantisation,
            engine=engine,
            total_vram_available_gb=float(gpu_info["vram_gb"] * gpu_count),
            estimated_vram_required_gb=0.0,
            headroom_gb=0.0,
            reasons=["VRAM requirement for this model is not known. Provide model parameter count to estimate."],
        )

    quant_key = quantisation.lower()
    quant_factor = QUANT_VRAM_FACTOR.get(quant_key, 1.0)
    base_vram = vram_fp16_gb * quant_factor
    kv_overhead = base_vram * KV_CACHE_OVERHEAD
    total_required = base_vram + kv_overhead

    total_available = float(gpu_info["vram_gb"]) * gpu_count

    headroom = total_available - total_required
    constraints: List[str] = []
    reasons: List[str] = []
    warnings: List[str] = []

    # Architecture check
    arch_gen_num = int(gpu_info["gen"].replace("sm_", ""))
    engine_min = ENGINE_MIN_ARCH.get(engine, 60)
    if arch_gen_num < engine_min:
        return CompatibilityResult(
            status="incompatible",
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            model_id=model_id,
            quantisation=quantisation,
            engine=engine,
            total_vram_available_gb=total_available,
            estimated_vram_required_gb=round(total_required, 1),
            headroom_gb=round(headroom, 1),
            gpu_arch=gpu_info["arch"],
            gpu_gen=gpu_info["gen"],
            reasons=[
                f"Engine '{engine}' requires GPU architecture {_gen_name(engine_min)} or newer. "
                f"'{gpu_model}' is {gpu_info['arch']} ({gpu_info['gen']})."
            ],
        )

    # VRAM check
    if headroom < 0:
        # Check if a more aggressive quantisation would fit
        for alt_quant, alt_factor in [("int8", 0.52), ("int4", 0.28), ("gguf", 0.30)]:
            alt_vram = vram_fp16_gb * alt_factor * (1 + KV_CACHE_OVERHEAD)
            if total_available - alt_vram >= 0 and alt_quant != quant_key:
                constraints.append(
                    f"Use {alt_quant} quantisation (requires ~{alt_vram:.1f} GB) to fit in {total_available:.0f} GB VRAM."
                )
                break

        if not constraints:
            return CompatibilityResult(
                status="incompatible",
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                model_id=model_id,
                quantisation=quantisation,
                engine=engine,
                total_vram_available_gb=total_available,
                estimated_vram_required_gb=round(total_required, 1),
                headroom_gb=round(headroom, 1),
                gpu_arch=gpu_info["arch"],
                gpu_gen=gpu_info["gen"],
                reasons=[
                    f"Model requires ~{total_required:.1f} GB VRAM at {quantisation} but only "
                    f"{total_available:.0f} GB available across {gpu_count}× {gpu_model}. "
                    "Add more GPUs or use a smaller quantisation."
                ],
            )
        else:
            status = "compatible_with_constraints"
    elif headroom < total_required * 0.1:
        # Less than 10% headroom — risky
        status = "compatible_with_constraints"
        warnings.append(
            f"Only {headroom:.1f} GB VRAM headroom. Under load with long contexts or large batches "
            "this may OOM. Reduce context length or batch size."
        )
    else:
        status = "compatible"

    # Context length warning
    if context_length and context_length > 32768:
        kv_extra = (context_length / 32768) * kv_overhead
        if headroom < kv_extra:
            status = "compatible_with_constraints"
            constraints.append(
                f"Long context ({context_length:,} tokens) adds ~{kv_extra:.1f} GB KV cache. "
                "Consider reducing context length or upgrading GPU."
            )

    # Performance estimate (very rough — real throughput depends on many factors)
    tflops = float(gpu_info.get("tflops_fp16", 0))
    if tflops and param_count_str:
        estimated_tps = _estimate_tps(tflops * gpu_count, param_count_str, quant_key)
    else:
        estimated_tps = None

    if estimated_tps:
        warnings.append(
            "Token-per-second estimate is a rough approximation based on FP16 TFLOPs. "
            "Actual throughput depends on batching, attention kernels, and system load."
        )

    reasons.append(
        f"Estimated VRAM: {total_required:.1f} GB (model) + KV cache ≈ {total_required:.1f} GB total. "
        f"Available: {total_available:.0f} GB across {gpu_count}× {gpu_model}. Headroom: {headroom:.1f} GB."
    )

    return CompatibilityResult(
        status=status,
        gpu_model=gpu_model,
        gpu_count=gpu_count,
        model_id=model_id,
        quantisation=quantisation,
        engine=engine,
        total_vram_available_gb=total_available,
        estimated_vram_required_gb=round(total_required, 1),
        headroom_gb=round(headroom, 1),
        constraints=constraints,
        reasons=reasons,
        warnings=warnings,
        estimated_tokens_per_second=estimated_tps,
        gpu_arch=gpu_info["arch"],
        gpu_gen=gpu_info["gen"],
    )


def _gen_name(sm: int) -> str:
    names = {60: "Pascal (sm_60)", 70: "Volta (sm_70)", 75: "Turing (sm_75)",
             80: "Ampere (sm_80)", 86: "Ampere (sm_86)", 89: "Ada (sm_89)", 90: "Hopper (sm_90)"}
    return names.get(sm, f"sm_{sm}")


def _estimate_tps(total_tflops: float, param_count_str: str, quant: str) -> Optional[float]:
    """Very rough token throughput estimate. Do not use for SLA guarantees."""
    try:
        s = param_count_str.upper().split()[0]
        multiplier = 1e9 if s.endswith("B") else 1e6
        params = float(s[:-1]) * multiplier
    except Exception:
        return None

    quant_speedup = {"fp16": 1.0, "int8": 1.6, "int4": 2.5, "awq": 2.4, "gptq": 2.3, "gguf": 2.0}
    speedup = quant_speedup.get(quant, 1.0)

    # Autoregressive token generation: ~2 × params FLOPs/token
    flops_per_token = 2 * params
    tps = (total_tflops * 1e12) / flops_per_token * speedup
    return round(tps, 1)


def recommend_gpus_for_model(
    vram_fp16_gb: float,
    quant: str = "int8",
    engine: str = "vllm",
) -> List[Dict[str, Any]]:
    """
    Return a ranked list of GPU configurations that can run this model.

    Returns configs sorted by cost-efficiency (more headroom per VRAM = better value).
    """
    recommendations = []
    quant_factor = QUANT_VRAM_FACTOR.get(quant, 1.0)
    required = vram_fp16_gb * quant_factor * (1 + KV_CACHE_OVERHEAD)

    for gpu_key, gpu_info in GPU_DB.items():
        engine_min = ENGINE_MIN_ARCH.get(engine, 60)
        arch_gen = int(gpu_info["gen"].replace("sm_", ""))
        if arch_gen < engine_min:
            continue

        # Try 1, 2, 4, 8 GPUs
        for count in [1, 2, 4, 8]:
            total = float(gpu_info["vram_gb"]) * count
            if total >= required:
                headroom_pct = (total - required) / total * 100
                recommendations.append({
                    "gpu_model": gpu_key,
                    "gpu_count": count,
                    "total_vram_gb": total,
                    "estimated_required_gb": round(required, 1),
                    "headroom_pct": round(headroom_pct, 1),
                    "arch": gpu_info["arch"],
                    "tflops_fp16": gpu_info.get("tflops_fp16", 0) * count,
                    "quantisation": quant,
                    "engine": engine,
                })
                break  # Don't recommend more GPUs of same model than needed

    # Sort: prefer single GPU, then fewest GPUs, then highest headroom
    recommendations.sort(key=lambda r: (r["gpu_count"], -r["headroom_pct"]))
    return recommendations[:10]
