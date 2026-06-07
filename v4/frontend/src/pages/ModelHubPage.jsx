import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../App.jsx'
import {
  Brain, Search, Filter, Zap, ExternalLink, Star, Download, Cpu,
  ChevronDown, Layers, Eye, Mic, Code2, MessageSquare, Box,
  ArrowRight, Sparkles, TrendingUp, Clock, Users, GitBranch
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════
   AI Model Catalog — Open Source Models for GPU Cloud
   ═══════════════════════════════════════════════════════════════════ */

const CATEGORIES = [
  { id: 'all', label: 'All Models', icon: Layers, color: '#7C6BF0' },
  { id: 'llm', label: 'Large Language', icon: MessageSquare, color: '#7C6BF0' },
  { id: 'vision', label: 'Vision & Image', icon: Eye, color: '#F472B6' },
  { id: 'audio', label: 'Audio & Speech', icon: Mic, color: '#10B981' },
  { id: 'code', label: 'Code Generation', icon: Code2, color: '#F59E0B' },
  { id: 'multimodal', label: 'Multimodal', icon: Sparkles, color: '#8B5CF6' },
  { id: 'embedding', label: 'Embeddings', icon: Box, color: '#06B6D4' },
]

const MODELS = [
  // ── Large Language Models ──────────────────────────────────────
  {
    id: 'llama-3.1-405b', name: 'LLaMA 3.1 405B', org: 'Meta AI',
    category: 'llm', params: '405B', license: 'Llama 3.1 Community',
    desc: 'Largest open-source LLM. Exceptional reasoning, multilingual support, and 128K context window. Matches GPT-4 class on most benchmarks.',
    tags: ['Flagship', '128K Context', 'Multilingual'], gpu_min: '8×A100 80GB',
    est_cost: '$3.20/hr', hf_url: 'https://huggingface.co/meta-llama/Llama-3.1-405B-Instruct',
    popularity: 98, trending: true, new: false,
  },
  {
    id: 'llama-3.1-70b', name: 'LLaMA 3.1 70B', org: 'Meta AI',
    category: 'llm', params: '70B', license: 'Llama 3.1 Community',
    desc: 'Best cost-performance ratio for production LLM workloads. 128K context, strong code and reasoning.',
    tags: ['Production', '128K Context', 'Fine-tunable'], gpu_min: '2×A100 80GB',
    est_cost: '$1.60/hr', hf_url: 'https://huggingface.co/meta-llama/Llama-3.1-70B-Instruct',
    popularity: 96, trending: true, new: false,
  },
  {
    id: 'llama-3.1-8b', name: 'LLaMA 3.1 8B', org: 'Meta AI',
    category: 'llm', params: '8B', license: 'Llama 3.1 Community',
    desc: 'Lightweight yet powerful. Ideal for fine-tuning, edge deployment, and budget-conscious inference.',
    tags: ['Lightweight', 'Fine-tunable', 'Edge'], gpu_min: '1×A10 24GB',
    est_cost: '$0.40/hr', hf_url: 'https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct',
    popularity: 94, trending: false, new: false,
  },
  {
    id: 'deepseek-v3', name: 'DeepSeek-V3', org: 'DeepSeek AI',
    category: 'llm', params: '671B MoE', license: 'MIT',
    desc: 'State-of-the-art MoE architecture. Outperforms GPT-4o on coding and math. 128K context with efficient sparse activation.',
    tags: ['MoE', 'SOTA', 'MIT License'], gpu_min: '8×H100 80GB',
    est_cost: '$4.80/hr', hf_url: 'https://huggingface.co/deepseek-ai/DeepSeek-V3',
    popularity: 97, trending: true, new: true,
  },
  {
    id: 'deepseek-r1', name: 'DeepSeek-R1', org: 'DeepSeek AI',
    category: 'llm', params: '671B MoE', license: 'MIT',
    desc: 'Reasoning-first model with chain-of-thought. Matches OpenAI o1 on complex reasoning tasks.',
    tags: ['Reasoning', 'Chain-of-Thought', 'MIT'], gpu_min: '8×H100 80GB',
    est_cost: '$4.80/hr', hf_url: 'https://huggingface.co/deepseek-ai/DeepSeek-R1',
    popularity: 95, trending: true, new: true,
  },
  {
    id: 'mistral-large-2', name: 'Mistral Large 2', org: 'Mistral AI',
    category: 'llm', params: '123B', license: 'Apache 2.0',
    desc: 'Multilingual powerhouse supporting 12 languages. Strong function calling and JSON mode.',
    tags: ['Multilingual', 'Function Calling', 'Apache'], gpu_min: '4×A100 80GB',
    est_cost: '$2.40/hr', hf_url: 'https://huggingface.co/mistralai/Mistral-Large-Instruct-2411',
    popularity: 90, trending: false, new: false,
  },
  {
    id: 'mixtral-8x22b', name: 'Mixtral 8×22B', org: 'Mistral AI',
    category: 'llm', params: '141B MoE', license: 'Apache 2.0',
    desc: 'Sparse MoE architecture. Uses only 39B active params for fast inference at 141B quality.',
    tags: ['MoE', 'Fast Inference', 'Apache'], gpu_min: '4×A100 80GB',
    est_cost: '$2.10/hr', hf_url: 'https://huggingface.co/mistralai/Mixtral-8x22B-Instruct-v0.1',
    popularity: 87, trending: false, new: false,
  },
  {
    id: 'qwen-2.5-72b', name: 'Qwen 2.5 72B', org: 'Alibaba Cloud',
    category: 'llm', params: '72B', license: 'Apache 2.0',
    desc: 'Excellent for Chinese & English. Long context up to 128K tokens with strong reasoning.',
    tags: ['Bilingual', '128K Context', 'Apache'], gpu_min: '2×A100 80GB',
    est_cost: '$1.60/hr', hf_url: 'https://huggingface.co/Qwen/Qwen2.5-72B-Instruct',
    popularity: 88, trending: true, new: false,
  },
  {
    id: 'gemma-2-27b', name: 'Gemma 2 27B', org: 'Google DeepMind',
    category: 'llm', params: '27B', license: 'Gemma Terms',
    desc: 'Knowledge-distilled from Gemini. Exceptional for its size. Great for local and edge deployments.',
    tags: ['Knowledge Distilled', 'Efficient', 'Edge'], gpu_min: '1×A100 80GB',
    est_cost: '$0.80/hr', hf_url: 'https://huggingface.co/google/gemma-2-27b-it',
    popularity: 85, trending: false, new: false,
  },
  {
    id: 'phi-4', name: 'Phi-4', org: 'Microsoft',
    category: 'llm', params: '14B', license: 'MIT',
    desc: 'Small model, big performance. Beats models 5× its size on reasoning benchmarks. MIT licensed.',
    tags: ['Compact', 'MIT License', 'Reasoning'], gpu_min: '1×RTX 4090',
    est_cost: '$0.35/hr', hf_url: 'https://huggingface.co/microsoft/phi-4',
    popularity: 86, trending: true, new: true,
  },

  // ── Vision & Image ────────────────────────────────────────────
  {
    id: 'flux-1-dev', name: 'FLUX.1 [dev]', org: 'Black Forest Labs',
    category: 'vision', params: '12B', license: 'FLUX.1 Non-commercial',
    desc: 'State-of-the-art text-to-image. Superior prompt adherence, photorealism, and typography rendering.',
    tags: ['Text-to-Image', 'Photorealistic', '12B'], gpu_min: '1×A100 80GB',
    est_cost: '$0.80/hr', hf_url: 'https://huggingface.co/black-forest-labs/FLUX.1-dev',
    popularity: 93, trending: true, new: false,
  },
  {
    id: 'sdxl-turbo', name: 'SDXL Turbo', org: 'Stability AI',
    category: 'vision', params: '3.5B', license: 'Stability Community',
    desc: 'Real-time image generation in 1-4 steps. Perfect for interactive applications and rapid prototyping.',
    tags: ['Real-time', '1-Step Gen', 'Interactive'], gpu_min: '1×RTX 4090',
    est_cost: '$0.35/hr', hf_url: 'https://huggingface.co/stabilityai/sdxl-turbo',
    popularity: 89, trending: false, new: false,
  },
  {
    id: 'stable-video', name: 'Stable Video Diffusion', org: 'Stability AI',
    category: 'vision', params: '1.5B', license: 'Stability Community',
    desc: 'Generate short video clips from a single image. 14-25 frames at 576×1024 resolution.',
    tags: ['Image-to-Video', '576×1024', 'Generative'], gpu_min: '1×A100 40GB',
    est_cost: '$0.80/hr', hf_url: 'https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt',
    popularity: 82, trending: false, new: false,
  },
  {
    id: 'sam-2', name: 'SAM 2', org: 'Meta AI',
    category: 'vision', params: '0.6B', license: 'Apache 2.0',
    desc: 'Segment Anything in images and videos. Zero-shot object segmentation with click/box prompts.',
    tags: ['Segmentation', 'Zero-Shot', 'Video'], gpu_min: '1×T4 16GB',
    est_cost: '$0.20/hr', hf_url: 'https://huggingface.co/facebook/sam2-hiera-large',
    popularity: 84, trending: false, new: false,
  },

  // ── Audio & Speech ────────────────────────────────────────────
  {
    id: 'whisper-large-v3-turbo', name: 'Whisper Large v3 Turbo', org: 'OpenAI',
    category: 'audio', params: '809M', license: 'MIT',
    desc: 'Fastest multilingual ASR. 8× faster than v3 with near-identical accuracy. 99+ languages.',
    tags: ['ASR', 'Multilingual', '8× Faster'], gpu_min: '1×T4 16GB',
    est_cost: '$0.20/hr', hf_url: 'https://huggingface.co/openai/whisper-large-v3-turbo',
    popularity: 92, trending: true, new: false,
  },
  {
    id: 'parler-tts', name: 'Parler TTS', org: 'Hugging Face',
    category: 'audio', params: '880M', license: 'Apache 2.0',
    desc: 'High-quality text-to-speech with natural prosody. Describe voice characteristics in plain text.',
    tags: ['TTS', 'Natural Voice', 'Apache'], gpu_min: '1×T4 16GB',
    est_cost: '$0.20/hr', hf_url: 'https://huggingface.co/parler-tts/parler-tts-large-v1',
    popularity: 78, trending: false, new: false,
  },

  // ── Code Generation ───────────────────────────────────────────
  {
    id: 'deepseek-coder-v2', name: 'DeepSeek-Coder-V2', org: 'DeepSeek AI',
    category: 'code', params: '236B MoE', license: 'MIT',
    desc: 'Best open-source coding model. 128K context, supports 338 languages, surpasses GPT-4o on HumanEval.',
    tags: ['338 Languages', 'SOTA Code', 'MIT'], gpu_min: '4×A100 80GB',
    est_cost: '$2.40/hr', hf_url: 'https://huggingface.co/deepseek-ai/DeepSeek-Coder-V2-Instruct',
    popularity: 91, trending: true, new: false,
  },
  {
    id: 'qwen-2.5-coder-32b', name: 'Qwen2.5-Coder 32B', org: 'Alibaba Cloud',
    category: 'code', params: '32B', license: 'Apache 2.0',
    desc: 'Matches GPT-4o on code completion. Supports 92 languages with excellent instruction following.',
    tags: ['Code Completion', '92 Languages', 'Apache'], gpu_min: '1×A100 80GB',
    est_cost: '$0.80/hr', hf_url: 'https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct',
    popularity: 86, trending: true, new: true,
  },
  {
    id: 'starcoder-2-15b', name: 'StarCoder2 15B', org: 'BigCode',
    category: 'code', params: '15B', license: 'BigCode OpenRAIL-M',
    desc: 'Trained on The Stack v2. Strong at code completion, infilling, and instruction following.',
    tags: ['Code Infill', 'The Stack v2', 'Open'], gpu_min: '1×RTX 4090',
    est_cost: '$0.35/hr', hf_url: 'https://huggingface.co/bigcode/starcoder2-15b',
    popularity: 79, trending: false, new: false,
  },

  // ── Multimodal ────────────────────────────────────────────────
  {
    id: 'llava-next-72b', name: 'LLaVA-NeXT 72B', org: 'LLaVA Team',
    category: 'multimodal', params: '72B', license: 'Apache 2.0',
    desc: 'Leading open-source vision-language model. Understands images, charts, documents, and diagrams.',
    tags: ['Vision-Language', 'Document AI', 'Apache'], gpu_min: '2×A100 80GB',
    est_cost: '$1.60/hr', hf_url: 'https://huggingface.co/llava-hf/llava-v1.6-mistral-7b-hf',
    popularity: 83, trending: false, new: false,
  },
  {
    id: 'internvl-2.5', name: 'InternVL 2.5 78B', org: 'OpenGVLab',
    category: 'multimodal', params: '78B', license: 'MIT',
    desc: 'Top multimodal model on OpenCompass. Excels at OCR, chart understanding, and visual QA.',
    tags: ['OCR', 'Chart QA', 'MIT License'], gpu_min: '2×A100 80GB',
    est_cost: '$1.60/hr', hf_url: 'https://huggingface.co/OpenGVLab/InternVL2_5-78B',
    popularity: 81, trending: true, new: true,
  },

  // ── Embeddings ────────────────────────────────────────────────
  {
    id: 'gte-qwen2-7b', name: 'GTE-Qwen2 7B', org: 'Alibaba DAMO',
    category: 'embedding', params: '7B', license: 'Apache 2.0',
    desc: '#1 on MTEB leaderboard. 8192 token context for long-document embeddings.',
    tags: ['MTEB #1', '8K Context', 'Apache'], gpu_min: '1×T4 16GB',
    est_cost: '$0.20/hr', hf_url: 'https://huggingface.co/Alibaba-NLP/gte-Qwen2-7B-instruct',
    popularity: 80, trending: true, new: false,
  },
  {
    id: 'nomic-embed-v1.5', name: 'Nomic Embed v1.5', org: 'Nomic AI',
    category: 'embedding', params: '137M', license: 'Apache 2.0',
    desc: 'Lightweight, Matryoshka embeddings. Truncate dimensions for faster search without retraining.',
    tags: ['Matryoshka', 'Lightweight', 'Apache'], gpu_min: 'CPU / T4',
    est_cost: '$0.05/hr', hf_url: 'https://huggingface.co/nomic-ai/nomic-embed-text-v1.5',
    popularity: 76, trending: false, new: false,
  },
]

/* ── Utility ──────────────────────────────────────────────────────── */
const formatParams = p => {
  if (p.includes('MoE')) return p
  const n = parseFloat(p)
  if (n >= 1000) return `${(n/1000).toFixed(1)}T`
  return p
}

/* ── Model Card ──────────────────────────────────────────────────── */
function ModelCard({ model, index, onDeploy }) {
  const cat = CATEGORIES.find(c => c.id === model.category)
  const CatIcon = cat?.icon || Brain
  const catColor = cat?.color || '#7C6BF0'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.04, ease: [0.25, 0.46, 0.45, 0.94] }}
      className="model-card"
    >
      {/* Gradient accent top border */}
      <div className="model-card-accent" style={{ background: `linear-gradient(90deg, ${catColor}, ${catColor}80)` }} />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
        <div className="model-card-icon" style={{ background: `${catColor}12`, border: `1px solid ${catColor}20` }}>
          <CatIcon size={18} color={catColor} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <h3 className="model-card-name">{model.name}</h3>
            {model.new && <span className="model-badge model-badge-new">NEW</span>}
            {model.trending && <span className="model-badge model-badge-trending"><TrendingUp size={9} /> Hot</span>}
          </div>
          <div className="model-card-org">{model.org}</div>
        </div>
        <div className="model-card-params" style={{ color: catColor }}>
          {formatParams(model.params)}
        </div>
      </div>

      {/* Description */}
      <p className="model-card-desc">{model.desc}</p>

      {/* Tags */}
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 14 }}>
        {model.tags.map(t => (
          <span key={t} className="model-tag">{t}</span>
        ))}
      </div>

      {/* Specs row */}
      <div className="model-card-specs">
        <div className="model-spec">
          <Cpu size={11} />
          <span>{model.gpu_min}</span>
        </div>
        <div className="model-spec">
          <Clock size={11} />
          <span>{model.est_cost}</span>
        </div>
        <div className="model-spec">
          <Users size={11} />
          <span>{model.popularity}% popular</span>
        </div>
      </div>

      {/* Footer */}
      <div className="model-card-footer">
        <a href={model.hf_url} target="_blank" rel="noopener noreferrer" className="model-link">
          <GitBranch size={12} /> HuggingFace
          <ExternalLink size={10} />
        </a>
        <span className="model-license">{model.license}</span>
        <button className="model-deploy-btn" onClick={() => onDeploy(model)}>
          <Zap size={12} /> Deploy
          <ArrowRight size={11} />
        </button>
      </div>
    </motion.div>
  )
}

/* ── Main Page ────────────────────────────────────────────────────── */
export default function ModelHubPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [sortBy, setSortBy] = useState('popularity')

  const filtered = useMemo(() => {
    let list = MODELS
    if (category !== 'all') list = list.filter(m => m.category === category)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(m =>
        m.name.toLowerCase().includes(q) ||
        m.org.toLowerCase().includes(q) ||
        m.desc.toLowerCase().includes(q) ||
        m.tags.some(t => t.toLowerCase().includes(q))
      )
    }
    if (sortBy === 'popularity') list = [...list].sort((a, b) => b.popularity - a.popularity)
    else if (sortBy === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name))
    else if (sortBy === 'new') list = [...list].sort((a, b) => (b.new ? 1 : 0) - (a.new ? 1 : 0) || b.popularity - a.popularity)
    return list
  }, [search, category, sortBy])

  const handleDeploy = (model) => {
    navigate(`/goals?goal=${encodeURIComponent(
      `Deploy ${model.name} (${model.params}) for inference using the cheapest available ${model.gpu_min} GPU`
    )}`)
  }

  const activeCat = CATEGORIES.find(c => c.id === category)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{ maxWidth: 1280 }}
    >
      {/* Hero Header */}
      <div className="model-hub-hero">
        <div className="model-hub-hero-glow" />
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
            <div className="model-hub-icon-wrap">
              <Brain size={22} color="#7C6BF0" />
            </div>
            <div>
              <h1 className="model-hub-title">AI Model Hub</h1>
              <p className="model-hub-subtitle">
                {MODELS.length} open-source models · One-click deploy to cheapest GPU
              </p>
            </div>
          </div>

          {/* Stats strip */}
          <div className="model-hub-stats">
            {[
              { label: 'Models', value: MODELS.length, icon: Brain, color: '#7C6BF0' },
              { label: 'Categories', value: CATEGORIES.length - 1, icon: Layers, color: '#F472B6' },
              { label: 'Trending', value: MODELS.filter(m => m.trending).length, icon: TrendingUp, color: '#10B981' },
              { label: 'New This Month', value: MODELS.filter(m => m.new).length, icon: Sparkles, color: '#F59E0B' },
            ].map(s => (
              <div key={s.label} className="model-hub-stat">
                <s.icon size={14} color={s.color} />
                <span className="model-hub-stat-value">{s.value}</span>
                <span className="model-hub-stat-label">{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Search + Filter Bar */}
      <div className="model-filter-bar">
        <div className="model-search-wrap">
          <Search size={16} color="#94A3B8" />
          <input
            type="text"
            placeholder="Search models, orgs, or tags..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="model-search-input"
          />
          {search && (
            <button onClick={() => setSearch('')} className="model-search-clear">×</button>
          )}
        </div>
        <div className="model-sort-wrap">
          <Filter size={13} color="#94A3B8" />
          <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="model-sort-select">
            <option value="popularity">Most Popular</option>
            <option value="new">Newest First</option>
            <option value="name">Alphabetical</option>
          </select>
        </div>
      </div>

      {/* Category Tabs */}
      <div className="model-category-tabs">
        {CATEGORIES.map(cat => {
          const Icon = cat.icon
          const isActive = category === cat.id
          const count = cat.id === 'all' ? MODELS.length : MODELS.filter(m => m.category === cat.id).length
          return (
            <button
              key={cat.id}
              onClick={() => setCategory(cat.id)}
              className={`model-category-tab ${isActive ? 'active' : ''}`}
              style={isActive ? { '--tab-color': cat.color } : {}}
            >
              <Icon size={14} />
              <span>{cat.label}</span>
              <span className="model-category-count">{count}</span>
            </button>
          )
        })}
      </div>

      {/* Results count */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: '#64748B', fontWeight: 600 }}>
          {filtered.length} model{filtered.length !== 1 ? 's' : ''}
          {category !== 'all' && ` in ${activeCat?.label}`}
          {search && ` matching "${search}"`}
        </span>
        {(search || category !== 'all') && (
          <button
            onClick={() => { setSearch(''); setCategory('all') }}
            style={{
              fontSize: 12, color: '#EF4444', background: 'rgba(239,68,68,0.06)',
              border: '1px solid rgba(239,68,68,0.15)', borderRadius: 6,
              padding: '3px 10px', cursor: 'pointer',
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Model Grid */}
      <div className="model-grid">
        <AnimatePresence mode="popLayout">
          {filtered.map((model, i) => (
            <ModelCard key={model.id} model={model} index={i} onDeploy={handleDeploy} />
          ))}
        </AnimatePresence>
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#94A3B8' }}>
          <Search size={32} style={{ display: 'block', margin: '0 auto 12px', opacity: 0.4 }} />
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>No models found</div>
          <div style={{ fontSize: 13 }}>Try adjusting your search or filters</div>
        </div>
      )}

      {/* Bottom CTA */}
      <div className="model-hub-cta">
        <Sparkles size={16} color="#7C6BF0" />
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>
            Don't see your model?
          </div>
          <div style={{ fontSize: 12, color: '#64748B' }}>
            Submit any HuggingFace model URL as a goal — OrQuanta will auto-configure the optimal GPU, provider, and runtime.
          </div>
        </div>
        <button
          onClick={() => navigate('/goals')}
          className="model-deploy-btn"
          style={{ marginLeft: 'auto', flexShrink: 0 }}
        >
          <Zap size={12} /> Custom Deploy
        </button>
      </div>
    </motion.div>
  )
}
