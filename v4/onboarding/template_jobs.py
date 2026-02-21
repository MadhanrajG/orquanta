"""
OrQuanta Agentic v1.0 — Pre-built Job Templates

Ready-to-run templates for common ML workloads.
Each template has:
  - Estimated cost, time, required VRAM
  - Pre-configured Docker image
  - One-click submission

Templates:
  1. PyTorch MNIST Training (beginner — $0.05)
  2. Stable Diffusion Image Generation ($0.25)
  3. LLM Fine-tuning with LoRA on LLaMA ($8.00)
  4. Whisper Audio Transcription ($0.15)
  5. Custom Python Script (bring your own code)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class JobTemplate:
    id: str
    name: str
    description: str
    category: str               # "beginner" | "intermediate" | "advanced"
    tags: list[str]
    gpu_type: str               # Preferred GPU type
    gpu_count: int
    required_vram_gb: int
    estimated_duration_min: int
    estimated_cost_usd: float
    docker_image: str
    command: str                # Shell command to run
    environment: dict[str, str] = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)    # Public datasets to mount
    output_artifacts: list[str] = field(default_factory=list)
    readme: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_job_request(self) -> dict[str, Any]:
        """Convert template to a /jobs/ POST request body."""
        return {
            "intent": self.description,
            "gpu_type": self.gpu_type,
            "gpu_count": self.gpu_count,
            "required_vram_gb": self.required_vram_gb,
            "max_cost_usd": self.estimated_cost_usd * 2,  # 2× buffer
            "docker_image": self.docker_image,
            "command": self.command,
            "environment": self.environment,
            "template_id": self.id,
        }


TEMPLATES: list[JobTemplate] = [

    JobTemplate(
        id="pytorch-mnist",
        name="PyTorch MNIST Training",
        description="Train a classic MNIST digit classifier in PyTorch. Perfect for verifying your GPU setup and understanding the workflow.",
        category="beginner",
        tags=["pytorch", "classification", "beginner", "cpu-compatible"],
        gpu_type="T4",
        gpu_count=1,
        required_vram_gb=4,
        estimated_duration_min=5,
        estimated_cost_usd=0.05,
        docker_image="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        command="""
python -c "
import torch, torch.nn as nn, torch.optim as optim
from torchvision import datasets, transforms
from torch.utils.data import DataLoader

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'Using device: {device}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')

transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
train_data = datasets.MNIST('/tmp/data', train=True, download=True, transform=transform)
loader = DataLoader(train_data, batch_size=256, shuffle=True, pin_memory=True)

model = nn.Sequential(nn.Flatten(), nn.Linear(784, 256), nn.ReLU(), nn.Linear(256, 10)).to(device)
opt = optim.Adam(model.parameters())
criterion = nn.CrossEntropyLoss()

for epoch in range(5):
    correct = total = 0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        opt.zero_grad()
        out = model(X)
        loss = criterion(out, y)
        loss.backward()
        opt.step()
        correct += (out.argmax(1) == y).sum().item()
        total += len(y)
    print(f'Epoch {epoch+1}/5 — Accuracy: {100*correct/total:.2f}%')

torch.save(model.state_dict(), '/artifacts/mnist_model.pt')
print('Model saved to /artifacts/mnist_model.pt')
"
        """.strip(),
        output_artifacts=["/artifacts/mnist_model.pt"],
        readme="Classic MNIST digit recognition. Trains in ~5 minutes on a T4 GPU. Great for verifying your cloud provider connection works.",
    ),

    JobTemplate(
        id="stable-diffusion",
        name="Stable Diffusion Image Generation",
        description="Generate high-quality images from text prompts using Stable Diffusion XL. Runs 50 inference steps.",
        category="intermediate",
        tags=["diffusion", "image-generation", "sdxl", "creative"],
        gpu_type="A100",
        gpu_count=1,
        required_vram_gb=16,
        estimated_duration_min=10,
        estimated_cost_usd=0.25,
        docker_image="stability/stable-diffusion:sdxl-1.0",
        command="""
pip install diffusers transformers accelerate torch --quiet
python -c "
from diffusers import StableDiffusionXLPipeline
import torch, os

pipe = StableDiffusionXLPipeline.from_pretrained(
    'stabilityai/stable-diffusion-xl-base-1.0',
    torch_dtype=torch.float16,
    use_safetensors=True,
    variant='fp16'
).to('cuda')

prompts = [
    'A futuristic data center filled with glowing GPU racks, cyberpunk aesthetic, dramatic lighting',
    'An AI robot orchestrating cloud computing resources, digital art, high quality',
    'Abstract visualization of neural network training, blue particles, 8K',
]

os.makedirs('/artifacts/images', exist_ok=True)
for i, prompt in enumerate(prompts):
    image = pipe(prompt=prompt, num_inference_steps=50, guidance_scale=7.5).images[0]
    path = f'/artifacts/images/output_{i+1}.png'
    image.save(path)
    print(f'Saved: {path}')

print('All images generated!')
"
        """.strip(),
        output_artifacts=["/artifacts/images/"],
        readme="Generates 3 images using Stable Diffusion XL. Uses fp16 for 2× speed. Images saved as PNG to the artifacts directory.",
    ),

    JobTemplate(
        id="llm-lora-finetune",
        name="LLM Fine-tuning with LoRA",
        description="Fine-tune Mistral 7B on a custom dataset using QLoRA (4-bit quantization + LoRA). Memory-efficient way to customize any 7B model.",
        category="advanced",
        tags=["llm", "fine-tuning", "lora", "qlora", "mistral", "nlp"],
        gpu_type="A100",
        gpu_count=1,
        required_vram_gb=24,
        estimated_duration_min=90,
        estimated_cost_usd=8.00,
        docker_image="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-devel",
        command="""
pip install transformers peft bitsandbytes datasets accelerate trl --quiet
python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer
from datasets import Dataset
import torch, json, os

print('=== OrQuanta LLM Fine-tuning with QLoRA ===')
print(f'GPU: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory // 1024**3}GB)')

model_name = 'mistralai/Mistral-7B-v0.1'
print(f'Loading {model_name}...')

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type='nf4',
    bnb_4bit_compute_dtype=torch.float16,
)
tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(model_name, quantization_config=bnb_config, device_map='auto')

lora_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    task_type=TaskType.CAUSAL_LM,
    target_modules=['q_proj', 'v_proj']
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# Sample dataset (replace with your own)
data = Dataset.from_list([
    {'text': 'Question: What is LoRA? Answer: Low-Rank Adaptation is a PEFT technique that adds trainable low-rank matrices.'},
    {'text': 'Question: How does QLoRA work? Answer: QLoRA combines 4-bit quantization with LoRA for memory-efficient fine-tuning.'},
] * 50)

training_args = TrainingArguments(
    output_dir='/artifacts/lora-model',
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    warmup_steps=10,
    logging_steps=10,
    save_steps=50,
    fp16=True,
    optim='paged_adamw_8bit',
    report_to='none',
)

trainer = SFTTrainer(
    model=model, args=training_args,
    train_dataset=data, dataset_text_field='text',
    max_seq_length=512,
)
trainer.train()
trainer.save_model('/artifacts/lora-model')
print('Fine-tuning complete! Model saved to /artifacts/lora-model')
"
        """.strip(),
        environment={"HF_TOKEN": "your-huggingface-token-here"},
        output_artifacts=["/artifacts/lora-model/"],
        readme="QLoRA fine-tuning of Mistral 7B in ~90 minutes on an A100. Uses 4-bit quantization to fit in 24GB. Replace the dataset with your own JSONL file.",
    ),

    JobTemplate(
        id="whisper-transcription",
        name="Whisper Audio Transcription",
        description="Transcribe audio files to text using OpenAI Whisper Large v3. Supports 100+ languages with word-level timestamps.",
        category="intermediate",
        tags=["whisper", "asr", "transcription", "audio", "nlp"],
        gpu_type="T4",
        gpu_count=1,
        required_vram_gb=8,
        estimated_duration_min=15,
        estimated_cost_usd=0.15,
        docker_image="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        command="""
pip install openai-whisper ffmpeg-python --quiet
python -c "
import whisper, json, os, urllib.request, time

print('Loading Whisper large-v3...')
model = whisper.load_model('large-v3')
print(f'Model loaded. Transcribing...')

# Demo: download a sample audio file
sample_url = 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'
audio_path = '/tmp/sample_audio.mp3'
print(f'Downloading sample audio from {sample_url}')
urllib.request.urlretrieve(sample_url, audio_path)

t0 = time.time()
result = model.transcribe(audio_path, verbose=False, word_timestamps=True)
duration = time.time() - t0

print(f'Transcription complete in {duration:.1f}s')
print(f'Detected language: {result[\"language\"]}')
print(f'Text preview: {result[\"text\"][:200]}...')

os.makedirs('/artifacts', exist_ok=True)
output = {
    'language': result['language'],
    'text': result['text'],
    'segments': result['segments'][:5],  # First 5 segments
    'duration_seconds': duration,
}
with open('/artifacts/transcription.json', 'w') as f:
    json.dump(output, f, indent=2)
print('Saved to /artifacts/transcription.json')
"
        """.strip(),
        output_artifacts=["/artifacts/transcription.json"],
        readme="Transcribes audio with Whisper large-v3. Replace the sample_url with your own audio file URL, or mount a volume with your files.",
    ),

    JobTemplate(
        id="custom-python",
        name="Custom Python Script",
        description="Run your own Python script on a GPU instance. Upload your script and specify requirements.txt.",
        category="beginner",
        tags=["custom", "python", "flexible"],
        gpu_type="A100",
        gpu_count=1,
        required_vram_gb=40,
        estimated_duration_min=30,
        estimated_cost_usd=1.20,
        docker_image="python:3.11-slim",
        command="""
# OrQuanta Custom Python Runner
# Upload your script as /scripts/main.py
# Add dependencies to /scripts/requirements.txt
pip install -r /scripts/requirements.txt --quiet 2>/dev/null
python /scripts/main.py
        """.strip(),
        volumes=["/scripts:/scripts"],
        environment={"PYTHONUNBUFFERED": "1"},
        readme="Bring your own Python script. Mount your code as a volume or copy it via SCP. Supports any public Python package via requirements.txt.",
    ),
]


TEMPLATES_BY_ID: dict[str, JobTemplate] = {t.id: t for t in TEMPLATES}


def get_template(template_id: str) -> JobTemplate | None:
    """Get a template by ID."""
    return TEMPLATES_BY_ID.get(template_id)


def get_all_templates(category: str | None = None) -> list[dict[str, Any]]:
    """List all templates, optionally filtered by category."""
    templates = TEMPLATES if not category else [t for t in TEMPLATES if t.category == category]
    return [t.to_dict() for t in templates]


def get_template_job_request(template_id: str) -> dict[str, Any] | None:
    """Get the job submission payload for a template."""
    template = get_template(template_id)
    return template.to_job_request() if template else None
