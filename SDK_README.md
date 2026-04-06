# OrQuanta Python SDK

> **AI-powered autonomous GPU cloud orchestration** — run GPU workloads 60% cheaper with zero infrastructure management.

```bash
pip install orquanta
```

## Quick Start

```python
from orquanta_sdk import OrQuantaClient

client = OrQuantaClient(api_key="oq_your_key_here")

# Submit a GPU job in one line
job = client.jobs.submit(
    intent="Fine-tune Llama 3 on my customer support dataset",
    gpu="H100",
    max_cost_usd=30.0,
)
print(f"Job {job.id} running on {job.provider} @ ${job.hourly_rate:.2f}/hr")

# Wait for completion
result = client.jobs.wait(job.id)
print(f"Done! Cost: ${result.cost_usd:.4f}")
```

## CLI Usage

```bash
# Login
orquanta login

# Submit a job
orquanta submit --intent "Run 3-epoch training on RTX 4090" --gpu RTX4090

# Watch jobs
orquanta jobs list

# Compare GPU pricing
orquanta pricing --gpu A100
```

## Features

- **Autonomous provider selection** — Automatically picks the cheapest GPU (RunPod, Lambda Labs, AWS, GCP)
- **Cost guardrails** — Hard budget limits per job; auto-terminates overrunning jobs
- **Live log streaming** — WebSocket stream of GPU execution logs
- **Zero config** — No SSH keys, no instance management, no cloud credentials required
- **14 AI agents** — Scheduling, cost optimization, self-healing, forecasting built-in

## License

MIT License. Copyright 2026 OrQuanta AI.
