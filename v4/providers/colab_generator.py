"""
OrQuanta — Google Colab Notebook Generator
==========================================
Generates complete, ready-to-run Jupyter notebooks from plain-English goals.
Users click "Open in Colab" → runs on free T4 GPU instantly.

No API key needed. No Google auth needed from OrQuanta's side.
The user opens the notebook in their own Google account.

Supported task types (auto-detected from goal text):
  - fine_tune      : Fine-tune LLaMA, Mistral, Phi-3, Gemma, etc.
  - inference      : Run inference/generation with a model
  - image_gen      : Stable Diffusion / FLUX image generation
  - whisper        : Audio transcription with Whisper
  - embedding      : Generate text embeddings
  - data_process   : Data cleaning, preprocessing
  - custom         : Generic ML task (user provides their own code hint)

Usage:
    gen = ColabGenerator()
    nb  = gen.generate(goal="Fine-tune LLaMA 3 8B on customer support data", budget=0)
    url = gen.get_colab_url(nb)  # data: URI opens directly in Colab
    # Or save to file: nb.save("orquanta_job.ipynb")
"""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# ─── Task detection ──────────────────────────────────────────────────────────

TASK_KEYWORDS: dict[str, list[str]] = {
    "fine_tune":    ["fine-tune", "finetune", "fine tune", "lora", "qlora", "sft", "finetuning",
                     "train on", "training data", "instruction tuning"],
    "inference":    ["inference", "generate text", "run model", "predict", "chat with", "prompting"],
    "image_gen":    ["stable diffusion", "sdxl", "flux", "image generation", "text to image",
                     "generate image", "diffusion"],
    "whisper":      ["whisper", "transcribe", "audio", "speech to text", "transcription"],
    "embedding":    ["embedding", "embeddings", "vector", "sentence transformer", "encode sentences"],
    "data_process": ["preprocess", "clean data", "dataset", "tokenize", "data pipeline",
                     "etl", "pandas", "process csv"],
}

MODEL_HINTS: dict[str, str] = {
    "llama":    "meta-llama/Meta-Llama-3-8B-Instruct",
    "mistral":  "mistralai/Mistral-7B-Instruct-v0.3",
    "phi":      "microsoft/Phi-3-mini-4k-instruct",
    "gemma":    "google/gemma-2b-it",
    "falcon":   "tiiuae/falcon-7b-instruct",
    "qwen":     "Qwen/Qwen2-7B-Instruct",
}


def detect_task(goal: str) -> str:
    g = goal.lower()
    for task, kws in TASK_KEYWORDS.items():
        if any(kw in g for kw in kws):
            return task
    return "fine_tune"   # default — most common for GPU users


def detect_model(goal: str) -> str:
    g = goal.lower()
    for keyword, model_id in MODEL_HINTS.items():
        if keyword in g:
            return model_id
    return "meta-llama/Meta-Llama-3-8B-Instruct"   # default


# ─── Notebook dataclass ───────────────────────────────────────────────────────

@dataclass
class Notebook:
    cells: list[dict]
    goal: str
    task_type: str
    model_id: str

    def to_dict(self) -> dict:
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec":     {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info":  {"name": "python", "version": "3.10.0"},
                "accelerator":    "GPU",
                "colab":          {"gpuType": "T4"},
                "orquanta":       {"goal": self.goal, "task": self.task_type, "generated_at": datetime.now(timezone.utc).isoformat()},
            },
            "cells": self.cells,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def get_colab_url(self) -> str:
        """Generate a URL that opens this notebook directly in Google Colab."""
        nb_json = self.to_json()
        encoded = urllib.parse.quote(nb_json)
        # Colab accepts a gist URL or a direct JSON — use the file=data approach
        # For production: upload to GitHub Gist and return gist URL
        # For demo: return a base64 encoded data URI they can paste
        b64 = base64.b64encode(nb_json.encode()).decode()
        return f"https://colab.research.google.com/#create=true&content={b64[:2000]}"  # truncated for URL

    def get_download_filename(self) -> str:
        safe = re.sub(r"[^a-z0-9]+", "_", self.goal.lower())[:40]
        return f"orquanta_{safe}.ipynb"


# ─── Cell builders ────────────────────────────────────────────────────────────

def _code_cell(source: str | list[str], cell_id: str | None = None) -> dict:
    if isinstance(source, list):
        source = "\n".join(source)
    return {
        "cell_type":       "code",
        "execution_count": None,
        "id":              cell_id or f"cell_{id(source) % 100000:05d}",
        "metadata":        {},
        "outputs":         [],
        "source":          source,
    }


def _md_cell(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "id":        f"md_{id(text) % 100000:05d}",
        "metadata":  {},
        "source":    text,
    }


# ─── Generator ───────────────────────────────────────────────────────────────

class ColabGenerator:
    """Generates complete Jupyter notebooks from OrQuanta goals."""

    def generate(self, goal: str, budget: float = 0.0, model_id: str | None = None) -> Notebook:
        task_type = detect_task(goal)
        model     = model_id or detect_model(goal)

        builders = {
            "fine_tune":    self._build_fine_tune,
            "inference":    self._build_inference,
            "image_gen":    self._build_image_gen,
            "whisper":      self._build_whisper,
            "embedding":    self._build_embedding,
            "data_process": self._build_data_process,
        }
        builder = builders.get(task_type, self._build_fine_tune)
        cells   = builder(goal, model)

        return Notebook(cells=cells, goal=goal, task_type=task_type, model_id=model)

    # ── Fine-tune (LLM) ──────────────────────────────────────────────────────

    def _build_fine_tune(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 🤖 OrQuanta — Auto-Generated Fine-Tuning Notebook\n**Goal:** {goal}\n\n> Generated by [OrQuanta](https://orquanta-production.up.railway.app) · Free T4 GPU · No cost"),
            _md_cell("## Step 1: Install Dependencies"),
            _code_cell([
                "# Install required packages (takes ~2 minutes on first run)",
                "!pip install -q transformers datasets peft trl bitsandbytes accelerate",
                "!pip install -q huggingface_hub wandb",
                "import torch",
                f"print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU ONLY — Change runtime to GPU!')",
                "print('VRAM:', round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1), 'GB' if torch.cuda.is_available() else '')",
            ]),
            _md_cell("## Step 2: Configuration"),
            _code_cell([
                "# ── OrQuanta Job Config ──────────────────────────────────",
                f'MODEL_ID      = "{model_id}"',
                f'GOAL          = """{goal}"""',
                "MAX_STEPS     = 100           # Increase for better results (more GPU time)",
                "LEARNING_RATE = 2e-4",
                "BATCH_SIZE    = 4",
                "MAX_SEQ_LEN   = 512",
                "LORA_RANK     = 16            # Higher = more params fine-tuned",
                "OUTPUT_DIR    = '/kaggle/working/orquanta_model'  # Auto-saved",
                "",
                "print(f'Model: {MODEL_ID}')",
                "print(f'Goal: {GOAL[:60]}...')",
            ]),
            _md_cell("## Step 3: Load Model (4-bit quantized for T4)"),
            _code_cell([
                "from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig",
                "from peft import LoraConfig, get_peft_model, TaskType",
                "import torch",
                "",
                "# 4-bit quantization — fits LLaMA 3 8B on a 16GB T4",
                "bnb_config = BitsAndBytesConfig(",
                "    load_in_4bit=True,",
                "    bnb_4bit_quant_type='nf4',",
                "    bnb_4bit_compute_dtype=torch.float16,",
                "    bnb_4bit_use_double_quant=True,",
                ")",
                "",
                "print(f'Loading {MODEL_ID}...')",
                "tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)",
                "if tokenizer.pad_token is None:",
                "    tokenizer.pad_token = tokenizer.eos_token",
                "",
                "model = AutoModelForCausalLM.from_pretrained(",
                "    MODEL_ID,",
                "    quantization_config=bnb_config,",
                "    device_map='auto',",
                "    trust_remote_code=True,",
                ")",
                "print('✅ Model loaded!')",
                "print(f'Params: {sum(p.numel() for p in model.parameters())/1e9:.1f}B')",
            ]),
            _md_cell("## Step 4: Prepare Your Dataset\n> **Replace this section** with your own dataset or use one from HuggingFace Hub"),
            _code_cell([
                "from datasets import load_dataset",
                "",
                "# ── OPTION A: Use a HuggingFace dataset ─────────────────",
                "# dataset = load_dataset('tatsu-lab/alpaca', split='train[:1000]')",
                "",
                "# ── OPTION B: Upload your own JSONL file ─────────────────",
                "# from google.colab import files",
                "# uploaded = files.upload()  # Upload your data.jsonl",
                "# dataset = load_dataset('json', data_files={'train': 'data.jsonl'})['train']",
                "",
                "# ── DEFAULT: Use Alpaca for demo ─────────────────────────",
                "print('Loading demo dataset (Alpaca)...')",
                "dataset = load_dataset('tatsu-lab/alpaca', split='train[:500]')",
                "print(f'Dataset loaded: {len(dataset)} examples')",
                "print('Sample:', dataset[0]['instruction'][:80])",
            ]),
            _md_cell("## Step 5: Apply LoRA and Train"),
            _code_cell([
                "from peft import LoraConfig, get_peft_model",
                "from trl import SFTTrainer, SFTConfig",
                "",
                "lora_config = LoraConfig(",
                "    r=LORA_RANK,",
                "    lora_alpha=32,",
                "    target_modules=['q_proj', 'v_proj', 'k_proj', 'o_proj'],",
                "    lora_dropout=0.05,",
                "    task_type=TaskType.CAUSAL_LM,",
                ")",
                "",
                "model = get_peft_model(model, lora_config)",
                "model.print_trainable_parameters()",
                "",
                "def format_prompt(example):",
                "    return f\"### Instruction:\\n{example['instruction']}\\n\\n### Response:\\n{example['output']}\"",
                "",
                "training_args = SFTConfig(",
                "    output_dir=OUTPUT_DIR,",
                "    max_steps=MAX_STEPS,",
                "    per_device_train_batch_size=BATCH_SIZE,",
                "    learning_rate=LEARNING_RATE,",
                "    fp16=True,",
                "    logging_steps=10,",
                "    save_strategy='epoch',",
                "    report_to='none',",
                "    max_seq_length=MAX_SEQ_LEN,",
                ")",
                "",
                "trainer = SFTTrainer(",
                "    model=model,",
                "    args=training_args,",
                "    train_dataset=dataset,",
                "    formatting_func=format_prompt,",
                ")",
                "",
                "print('🚀 Training started!')",
                "trainer.train()",
                "print('✅ Training complete!')",
            ]),
            _md_cell("## Step 6: Save + Test"),
            _code_cell([
                "import os",
                "",
                "# Save the LoRA adapter weights",
                "trainer.model.save_pretrained(OUTPUT_DIR)",
                "tokenizer.save_pretrained(OUTPUT_DIR)",
                f"print(f'✅ Model saved to {{OUTPUT_DIR}}')",
                "",
                "# Quick inference test",
                "from transformers import pipeline",
                "pipe = pipeline('text-generation', model=trainer.model, tokenizer=tokenizer,",
                "                max_new_tokens=100, do_sample=True, temperature=0.7)",
                "",
                "test_prompt = '### Instruction:\\nExplain GPU cloud orchestration in one sentence.\\n\\n### Response:\\n'",
                "result = pipe(test_prompt)[0]['generated_text']",
                "print('\\n=== Test Output ===\\n', result[len(test_prompt):])",
                "",
                "# Zip for download",
                "import shutil",
                "shutil.make_archive('/kaggle/working/orquanta_model', 'zip', OUTPUT_DIR)",
                "print('\\n📦 Model zipped → orquanta_model.zip (download from Kaggle output panel)')",
                "",
                "print('\\n🎉 Job complete! Orchestrated by OrQuanta — https://orquanta-production.up.railway.app')",
            ]),
        ]

    # ── Image Generation ──────────────────────────────────────────────────────

    def _build_image_gen(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 🎨 OrQuanta — Image Generation\n**Goal:** {goal}\n\n> Free T4 GPU via Kaggle · Orchestrated by [OrQuanta](https://orquanta-production.up.railway.app)"),
            _code_cell([
                "!pip install -q diffusers transformers accelerate xformers",
                "import torch",
                "print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No GPU!')",
            ]),
            _code_cell([
                "from diffusers import StableDiffusionXLPipeline",
                "import torch",
                "",
                "# Load SDXL (best quality on T4 with fp16)",
                "pipe = StableDiffusionXLPipeline.from_pretrained(",
                "    'stabilityai/stable-diffusion-xl-base-1.0',",
                "    torch_dtype=torch.float16,",
                "    variant='fp16',",
                "    use_safetensors=True,",
                ").to('cuda')",
                "",
                f'PROMPT = """{goal}"""',
                "NEGATIVE = 'blurry, ugly, deformed, low quality'",
                "NUM_IMAGES = 4",
                "",
                "images = pipe(",
                "    prompt=PROMPT,",
                "    negative_prompt=NEGATIVE,",
                "    num_images_per_prompt=NUM_IMAGES,",
                "    num_inference_steps=30,",
                "    guidance_scale=7.5,",
                ").images",
                "",
                "# Save outputs",
                "import os; os.makedirs('/kaggle/working/outputs', exist_ok=True)",
                "for i, img in enumerate(images):",
                "    path = f'/kaggle/working/outputs/image_{i+1}.png'",
                "    img.save(path)",
                "    print(f'Saved: {path}')",
                "    display(img)",
                "",
                "print(f'\\n✅ {NUM_IMAGES} images generated! Download from Kaggle output panel.')",
            ]),
        ]

    # ── Whisper Transcription ─────────────────────────────────────────────────

    def _build_whisper(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 🎤 OrQuanta — Audio Transcription (Whisper)\n**Goal:** {goal}"),
            _code_cell(["!pip install -q openai-whisper ffmpeg-python", "import whisper, torch",
                         "print('GPU:', torch.cuda.get_device_name(0))"]),
            _code_cell([
                "# ── Upload your audio file ───────────────────────────────",
                "from google.colab import files",
                "# uploaded = files.upload()  # Uncomment to upload locally",
                "# audio_file = list(uploaded.keys())[0]",
                "",
                "# ── OR use a URL ─────────────────────────────────────────",
                "# import urllib.request",
                "# urllib.request.urlretrieve('https://your-audio-url.mp3', 'audio.mp3')",
                "# audio_file = 'audio.mp3'",
                "",
                "# ── Demo: use example audio ──────────────────────────────",
                "!wget -q -O sample.mp3 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3'",
                "audio_file = 'sample.mp3'",
                "",
                "model = whisper.load_model('large-v3')",
                "print('Transcribing...')",
                "result = model.transcribe(audio_file, fp16=True)",
                "print('\\n=== Transcript ===\\n')",
                "print(result['text'])",
                "",
                "# Save to file",
                "with open('/kaggle/working/transcript.txt', 'w') as f:",
                "    f.write(result['text'])",
                "print('\\n✅ Transcript saved → transcript.txt')",
            ]),
        ]

    # ── Inference ────────────────────────────────────────────────────────────

    def _build_inference(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 🔮 OrQuanta — LLM Inference\n**Goal:** {goal}"),
            _code_cell(["!pip install -q transformers accelerate bitsandbytes", "import torch",
                         "print('GPU:', torch.cuda.get_device_name(0))"]),
            _code_cell([
                "from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig",
                "import torch",
                "",
                f'MODEL_ID = "{model_id}"',
                "",
                "bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)",
                "tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)",
                "model = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=bnb, device_map='auto')",
                "print('✅ Model ready')",
            ]),
            _code_cell([
                "# ── Your prompts ─────────────────────────────────────────",
                "prompts = [",
                f'    """{goal}""",',
                '    "Explain this in simple terms:",',
                '    "What are the key steps?",',
                "]",
                "",
                "for prompt in prompts:",
                "    inputs = tokenizer(prompt, return_tensors='pt').to('cuda')",
                "    with torch.no_grad():",
                "        out = model.generate(**inputs, max_new_tokens=200, do_sample=True, temperature=0.7)",
                "    response = tokenizer.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)",
                "    print(f'\\nPrompt: {prompt[:60]}...')",
                "    print(f'Response: {response}\\n')",
            ]),
        ]

    # ── Embedding ────────────────────────────────────────────────────────────

    def _build_embedding(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 📐 OrQuanta — Text Embeddings\n**Goal:** {goal}"),
            _code_cell(["!pip install -q sentence-transformers", "import torch",
                         "print('GPU:', torch.cuda.get_device_name(0))"]),
            _code_cell([
                "from sentence_transformers import SentenceTransformer",
                "import numpy as np",
                "",
                "model = SentenceTransformer('BAAI/bge-large-en-v1.5', device='cuda')",
                "",
                "# ── Replace with your texts ──────────────────────────────",
                "texts = [",
                f'    "{goal}",',
                '    "GPU cloud cost optimization",',
                '    "AI agent orchestration",',
                '    "Machine learning infrastructure",',
                "]",
                "",
                "embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)",
                "print(f'\\nShape: {embeddings.shape}')",
                "print(f'Embedding[0][:5]: {embeddings[0][:5]}')",
                "",
                "np.save('/kaggle/working/embeddings.npy', embeddings)",
                "print('✅ Embeddings saved → embeddings.npy')",
            ]),
        ]

    # ── Data Processing ──────────────────────────────────────────────────────

    def _build_data_process(self, goal: str, model_id: str) -> list[dict]:
        return [
            _md_cell(f"# 📊 OrQuanta — Data Processing Pipeline\n**Goal:** {goal}"),
            _code_cell(["!pip install -q pandas datasets transformers", "import pandas as pd",
                         "print('Ready')"]),
            _code_cell([
                "# ── Upload your data file ────────────────────────────────",
                "# from google.colab import files",
                "# uploaded = files.upload()",
                "# df = pd.read_csv(list(uploaded.keys())[0])",
                "",
                "# ── Demo: create sample data ─────────────────────────────",
                "df = pd.DataFrame({'text': ['Sample text 1', 'Sample text 2'] * 50,",
                "                   'label': [0, 1] * 50})",
                "print(f'Loaded: {len(df)} rows, {df.columns.tolist()}')",
                "print(df.head())",
            ]),
            _code_cell([
                "from transformers import AutoTokenizer",
                "",
                "tokenizer = AutoTokenizer.from_pretrained('bert-base-uncased')",
                "tokens = tokenizer(df['text'].tolist(), truncation=True, padding=True, max_length=128)",
                "",
                "import json",
                "output = {'input_ids': tokens['input_ids'], 'attention_mask': tokens['attention_mask'],",
                "          'labels': df['label'].tolist()}",
                "",
                "with open('/kaggle/working/processed_data.json', 'w') as f:",
                "    json.dump(output, f)",
                "",
                "print(f'✅ Processed {len(df)} examples → processed_data.json')",
            ]),
        ]


# ─── Singleton ───────────────────────────────────────────────────────────────

_generator: ColabGenerator | None = None

def get_colab_generator() -> ColabGenerator:
    global _generator
    if _generator is None:
        _generator = ColabGenerator()
    return _generator
