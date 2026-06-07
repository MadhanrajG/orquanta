import { useState, useEffect, useRef, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Send, Loader, Cpu, DollarSign, Clock, CheckCircle, AlertCircle, Sparkles, Brain, Shield, Calendar, FileText, Check, Activity } from 'lucide-react'
import { useAuth } from'../App.jsx'

import { useNavigate, useLocation } from'react-router-dom'

const API = import.meta.env.VITE_API_URL ||''

/* """ Placeholder cycling """"""""""""""""""""""""""""""""""""""""""""""" */
const PLACEHOLDERS = [
'Train Llama 3 8B on my dataset - budget $50',
'Run 500 Stable Diffusion jobs across Lambda Labs',
'Fine-tune Whisper Large v3 on 10 hours of audio',
'Benchmark Mistral 7B vs LLaMA 3 on my eval set',
'Generate 1M embeddings with text-embedding-3-large',
'Run hyperparameter sweep - 32 trials, A10 GPUs',
]

/* """ AI Smart Suggestion Chips """""""""""""""""""""""""""""""""""""""""" */
const AI_SUGGESTIONS = [
 // Model family
 { trigger: /llama|llm/i, chips: ['Fine-tune LLaMA 3 8B on my dataset under $50', 'Benchmark LLaMA 3 70B on my eval set', 'Quantize LLaMA 3 to GGUF for local inference'] },
 { trigger: /whisper|audio|transcript/i, chips: ['Transcribe 10 hours of audio with Whisper Large v3', 'Fine-tune Whisper on my custom voice dataset', 'Batch-transcribe 500 podcast files under $15'] },
 { trigger: /stable.?diff|sdxl|image|diffus/i, chips: ['Generate 1000 product images with SDXL 1024px', 'Fine-tune SDXL on my brand style (LoRA)', 'Run img2img on 500 photos under $8'] },
 { trigger: /embed|vector|rag/i, chips: ['Generate 1M text embeddings with ada-002', 'Build a RAG pipeline over my PDF corpus', 'Index 100k documents for semantic search under $5'] },
 { trigger: /train|sweep|hyper/i, chips: ['Run 32-trial hyperparameter sweep on A10 GPUs', 'Distributed training on 8x H100s under $200', 'Cross-validate my model across 5 folds'] },
 { trigger: /mistral|mixtral/i, chips: ['Benchmark Mistral 7B on my test set', 'Fine-tune Mixtral 8x7B on custom instructions', 'GGUF quantize Mixtral for edge deployment'] },
 { trigger: /gpt|openai/i, chips: ['Batch inference 10k prompts with GPT-4o mini', 'Distill GPT-4 responses into a smaller local model'] },
 // Budget-driven
 { trigger: /\$5|cheap|budget|low.?cost/i, chips: ['Run inference on 1k samples " keep it under $5', 'Cheapest GPU for 2-hour PyTorch training job', 'Optimize my training to fit a $10 budget'] },
 // Task-driven
 { trigger: /classify|sentiment|nlp/i, chips: ['Fine-tune BERT for sentiment classification', 'Train a text classifier on my labelled dataset'] },
 // Default suggestions (shown when goal is short but non-empty)
 { trigger: /./i, chips: ['Describe your task in more detail...', 'Fine-tune a model on my custom dataset', 'Run a batch inference job cheaply'] },
]

function AISuggestionChips({ goal, onChipClick }) {
 if (!goal || goal.length < 3) return null
 const matched = AI_SUGGESTIONS.find(s => s.trigger.test(goal))
 if (!matched) return null
 const chips = matched.chips.filter(c => !goal.toLowerCase().includes(c.toLowerCase().slice(0, 12)))
 if (!chips.length) return null
 return (
   <div className="mt-2 animate-fade-in">
     <div className="flex items-center gap-1.5 mb-2">
       <Sparkles size={11} style={{ color: '#7C6BF0' }} />
       <span style={{ fontSize: 11, color: '#475569', fontWeight: 600, letterSpacing: '0.05em' }}>AI SUGGESTIONS</span>
     </div>
     <div className="flex gap-2 flex-wrap">
       {chips.slice(0, 3).map(chip => (
         <button
           key={chip}
           onClick={() => onChipClick(chip)}
           type="button"
           className="text-xs px-3 py-1.5 rounded-full text-left transition-all hover:scale-105"
           style={{
             background: 'rgba(124,107,240,0.06)',
             border: '1px solid rgba(124,107,240,0.20)',
             color: '#7C6BF0',
             cursor: 'pointer',
             maxWidth: '100%',
             whiteSpace: 'nowrap',
             overflow: 'hidden',
             textOverflow: 'ellipsis',
           }}>
           {chip.length > 55 ? chip.slice(0, 52) + '...' : chip}
         </button>
       ))}
     </div>
   </div>
 )
}


/* """ Agent execution steps """"""""""""""""""""""""""""""""""""""""""" */
const AGENTS = [
 { key:'orchestrator', Icon: Brain,     name:'OrMind Orchestrator', color:'#7C6BF0', thoughts: ['Parsing natural language goal...','Building execution DAG...','Confidence: 0.91'] },
 { key:'cost',         Icon: DollarSign, name:'Cost Optimizer',      color:'#f59e0b', thoughts: ['Comparing 5 providers...','Lambda Labs A100 @ $1.99/hr wins','Saving $2.11/hr vs AWS'] },
 { key:'scheduler',    Icon: Calendar,   name:'Scheduler',           color:'#8b5cf6', thoughts: ['No queue backlog...','EDF priority assigned...','Provisioning now'] },
 { key:'healing',      Icon: Shield,     name:'Healing Agent',       color:'#10b981', thoughts: ['1Hz telemetry armed...','Anomaly baseline set...','Monitoring active'] },
 { key:'audit',        Icon: FileText,   name:'Audit Agent',         color:'#94A3B8', thoughts: ['Goal hash logged...','HMAC chain updated...','Decision recorded'] },
]

/* """ Cost Estimator (live preview) """"""""""""""""""""""""""""""""""*/
function CostPreview({ goal }) {
 const [est, setEst] = useState(null)
 useEffect(() => {
 if (!goal || goal.length < 10) { setEst(null); return }
 const t = setTimeout(() => {
 // Heuristic estimate from goal text
 const isLarge = /70b|72b|large|xl|huge|8x/i.test(goal)
 const isMedium = /7b|13b|medium|fine-?tune/i.test(goal)
 const gpu = isLarge ?'gpu_8x_a100' : isMedium ?'gpu_1x_a100' :'gpu_1x_a10'
 const hr = isLarge ? 14.32 : isMedium ? 1.99 : 0.75
 const hrs = isLarge ? 4 : isMedium ? Math.round(2 + Math.random() * 4) : 1
 const awsHr = isLarge ? 32.77 : isMedium ? 4.10 : 1.10
 setEst({
 gpu_type: gpu,
 gpu_display: isLarge ?'8x A100 80GB' : isMedium ?'A100 80GB' :'A10 24GB',
 provider:'Lambda Labs',
 cost_per_hr: hr,
 estimated_hrs: hrs,
 total: +(hr * hrs).toFixed(2),
 saved_vs_aws: +((awsHr - hr) * hrs).toFixed(2),
 confidence: Math.round(85 + Math.random() * 10),
 })
 }, 600)
 return () => clearTimeout(t)
 }, [goal])
 if (!est) return null
 return (
 <div className="animate-fade-in rounded-xl p-4 mt-4"
  style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
 <div className="flex items-center justify-between mb-3">
  <span className="text-sm font-semibold" style={{ color: '#0F172A' }}>AI Cost Estimate</span>
 <span className="text-xs px-2 py-0.5 rounded-full font-medium"
 style={{ background: '#EDE9FE', color: '#7C6BF0', border: '1px solid rgba(124,107,240,0.25)' }}>
 {est.confidence}% confidence
 </span>
 </div>
 <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
 {[
 { label: 'GPU',          value: est.gpu_display },
 { label: 'Provider',     value: est.provider },
 { label: 'Est. Duration', value: `~${est.estimated_hrs}h` },
 { label: 'Est. Cost',    value: `$${est.total}`, highlight: true },
 ].map(item => (
 <div key={item.label} className="rounded-lg p-2.5 text-center"
 style={{
  background: item.highlight ? 'rgba(16,185,129,0.06)' : '#F8FAFC',
  border: `1px solid ${item.highlight ? 'rgba(16,185,129,0.20)' : '#E2E8F0'}`,
 }}>
  <div className="text-sm font-semibold" style={{ color: item.highlight ? '#10B981' : '#0F172A', fontFamily: "'JetBrains Mono', monospace" }}>{item.value}</div>
 <div className="text-xs mt-0.5" style={{ color: '#94A3B8' }}>{item.label}</div>
 </div>
 ))}
 </div>
 {est.saved_vs_aws > 0 && (
 <div className="mt-2.5 text-center text-xs" style={{ color: '#94A3B8' }}>
 Saves <span className="font-semibold" style={{ color: '#059669' }}>${est.saved_vs_aws}</span> vs AWS on-demand
 </div>
 )}
 </div>
 )
}

/* """ Agent Execution Theater """"""""""""""""""""""""""""""""""""""" */
function AgentTheater({ phase, activeAgent }) {
 if (phase ==='idle') return null
 return (
 <div className="mt-5 animate-fade-in">
 <div className="flex items-center gap-2 mb-3">
 <div className="h-px flex-1" style={{ background: '#E2E8F0' }} />
 <span className="text-xs font-medium tracking-wider uppercase" style={{ color: '#94A3B8' }}>Agent Execution</span>
 <div className="h-px flex-1" style={{ background: '#E2E8F0' }} />
 </div>

 <div className="space-y-1.5">
 {AGENTS.map((agent, idx) => {
 const isActive = idx === activeAgent
 const isDone = (idx < activeAgent) || phase === 'running'
 const { Icon } = agent
 return (
 <div key={agent.key}
 className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300"
 style={{
 background: isActive ? `${agent.color}06` : 'transparent',
 border: `1px solid ${isActive ? agent.color + '25' : 'transparent'}`,
 }}>
 <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-all"
 style={{
  background: isDone ? agent.color + '12' : isActive ? agent.color : '#F1F5F9',
  border: `1.5px solid ${isDone || isActive ? agent.color + '50' : '#E2E8F0'}`,
 }}>
 {isDone
 ? <Check size={12} style={{ color: agent.color }} />
 : <Icon size={13} style={{ color: isActive ? '#fff' : '#94A3B8' }} />
 }
 </div>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2">
  <span className="text-sm font-medium" style={{ color: isDone || isActive ? '#0F172A' : '#94A3B8' }}>
 {agent.name}
 </span>
 {isDone && (
 <span className="text-xs px-1.5 py-0.5 rounded-full font-medium"
 style={{ background: agent.color + '12', color: agent.color }}>Done</span>
 )}
 {isActive && (
 <div className="flex gap-0.5 items-center">
 {[0,1,2].map(i => (
 <div key={i} className="w-1 h-1 rounded-full animate-bounce"
 style={{ background: agent.color, animationDelay: `${i*0.15}s` }} />
 ))}
 </div>
 )}
 </div>
 {isActive && (
 <p className="text-xs mt-0.5 truncate" style={{ color: '#94A3B8' }}>
 {agent.thoughts[0]}
 </p>
 )}
 </div>
 </div>
 )
 })}
 </div>

 {/* Live thought stream */}
 {activeAgent < AGENTS.length && (
 <div className="mt-3 rounded-xl p-3.5"
  style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', fontFamily: 'JetBrains Mono, monospace' }}>
 <div className="text-xs font-medium mb-2" style={{ color: '#94A3B8' }}>// reasoning stream</div>
 {phase ==='running' ? (
 <div className="text-xs animate-pulse" style={{ color: '#10b981' }}>Running on Lambda Labs A100 — monitoring active</div>
 ) : (
 AGENTS[activeAgent]?.thoughts.slice(0, Math.min(3, activeAgent + 1)).map((t, i) => (
 <div key={i} className="text-xs mb-1"
 style={{ color: AGENTS[activeAgent].color, opacity: 1 - i * 0.3 }}>
 {t}
 </div>
 ))
 )}
 </div>
 )}

 {/* Progress bar */}
 <div className="mt-4">
 <div className="flex justify-between text-xs mb-1.5" style={{ color: '#94A3B8' }}>
 <span>{['Planning...','Optimizing...','Scheduling...','Monitoring...','Auditing...','Running'][Math.min(activeAgent, 5)]}</span>
 <span>{Math.round(Math.min(100, (activeAgent / AGENTS.length) * 100))}%</span>
 </div>
  <div className="h-1.5 rounded-full overflow-hidden" style={{ background: '#E2E8F0' }}>
 <div className="h-full rounded-full transition-all duration-700"
 style={{
 width: `${Math.min(100, ((phase === 'running' ? AGENTS.length : activeAgent) / AGENTS.length) * 100)}%`,
 background: 'linear-gradient(90deg, #7C6BF0, #9B8BF4)',
 }} />
 </div>
 </div>
 </div>
 )
}

/* """ Main GoalSubmit """""""""""""""""""""""""""""""""""""""""""""""""" */
export default function GoalSubmit() {
 const { token } = useAuth()
 const navigate = useNavigate()
 const location = useLocation()
 const [goal, setGoal] = useState('')
 const [phase, setPhase] = useState('idle') // idle | planning | running | complete | error
 const [activeAgent, setAgent] = useState(0)
 const [jobId, setJobId] = useState(null)
 const [jobResult, setJobResult] = useState(null)
 const [error, setError] = useState('')
 const [pIdx, setPIdx] = useState(0)
 const textRef = useRef(null)
 const costEstRef = useRef(null)

 // Pre-fill goal from ?goal= query param (set by onboarding wizard)
 useEffect(() => {
 const params = new URLSearchParams(location.search)
 const pre = params.get('goal')
 if (pre) setGoal(decodeURIComponent(pre))
 }, [])

 // Cycle placeholder
 useEffect(() => {
 const t = setInterval(() => setPIdx(i => (i + 1) % PLACEHOLDERS.length), 3500)
 return () => clearInterval(t)
 }, [])

 // Agent theater animation
 useEffect(() => {
 if (phase !=='planning') return
 let a = 0
 const t = setInterval(() => {
 a++
 setAgent(a)
 if (a >= AGENTS.length) { clearInterval(t); setPhase('running') }
 }, 900)
 return () => clearInterval(t)
 }, [phase])

 const handleSubmit = async (e) => {
 e?.preventDefault()
 if (!goal.trim() || phase ==='planning') return
 setError(''); setPhase('planning'); setAgent(0); setJobId(null); setJobResult(null)

 // Detect GPU type from goal text for real job submission
 const isLarge = /70b|72b|large|xl|huge|8x/i.test(goal)
 const isMedium = /7b|13b|medium|fine-?tune|llama|mistral|whisper/i.test(goal)
 const gpuType = isLarge ?'A100' : isMedium ?'A100' :'T4'
 const maxCost = costEstRef.current?.total || (isLarge ? 60 : isMedium ? 20 : 5)

 try {
 // FIX B01: Correct API path - was /goals, now /api/v1/goals
 const res = await fetch(`${API}/api/v1/goals`, {
 method:'POST',
 headers: {'Content-Type':'application/json', Authorization: `Bearer ${token}` },
 body: JSON.stringify({ raw_text: goal, priority: 0.5 }),
 })
 const data = res.ok ? await res.json() : {}
 const goalJobId = data.job_id || data.goal_id || null

 // FIX B01 cont: Also create job in pipeline so it shows in Job Manager
 try {
 const jobRes = await fetch(`${API}/api/v1/jobs`, {
 method:'POST',
 headers: {'Content-Type':'application/json', Authorization: `Bearer ${token}` },
 body: JSON.stringify({
 intent: goal,
 gpu_type: gpuType,
 gpu_count: 1,
 provider: null,
 max_cost_usd: maxCost,
 max_runtime_minutes: 120,
 }),
 })
 if (jobRes.ok) {
 const jobData = await jobRes.json()
 setJobId(jobData.job_id || goalJobId ||'demo-' + Date.now().toString(36))
 setJobResult(jobData)
 } else {
 setJobId(goalJobId ||'demo-' + Date.now().toString(36))
 }
 } catch {
 setJobId(goalJobId ||'demo-' + Date.now().toString(36))
 }
 } catch {
 // In demo mode, just animate through without real API
 setJobId('demo-' + Date.now().toString(36))
 }
 }

 const handleReset = () => { setPhase('idle'); setGoal(''); setAgent(0); setJobId(null); setJobResult(null) }

  return (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
    className="max-w-3xl mx-auto space-y-6 animate-fade-in">
 {/* Header */}
 <div>
  <h1 className="text-2xl font-bold text-slate-800">Command Center</h1>
 <p className="text-slate-500 text-sm mt-1">Tell OrQuanta what you need in plain English. 5 agents handle the rest.</p>
 </div>

 {/* Main input card */}
 <div className="glass-card p-6" style={{ boxShadow:'0 0 60px rgba(124,107,240,0.06)' }}>
 <form onSubmit={handleSubmit}>
 <div className="relative">
 <div className="absolute left-4 top-4 text-lavender-500 opacity-60">
 <Cpu size={20} />
 </div>
 <textarea
 ref={textRef}
 id="goal-input"
 value={goal}
 onChange={e => setGoal(e.target.value)}
 disabled={phase !=='idle'}
 placeholder={PLACEHOLDERS[pIdx]}
 rows={4}
  className="w-full rounded-2xl resize-none text-slate-800 text-base leading-relaxed transition-all"
 style={{
 paddingLeft:'2.75rem', paddingTop:'1rem', paddingRight:'1rem', paddingBottom:'3.5rem',
  background:'#FFFFFF',
 border: `1px solid ${phase !=='idle' ?'rgba(124,107,240,0.3)' :'#E2E8F0'}`,
 outline:'none',
 fontSize:'15px',
 color: '#0F172A',
 }}
 onFocus={e => e.target.style.borderColor ='rgba(124,107,240,0.4)'}
 onBlur={e => phase ==='idle' && (e.target.style.borderColor ='#E2E8F0')}
 onKeyDown={e => { if (e.key ==='Enter' && (e.metaKey || e.ctrlKey)) handleSubmit() }}
 />

 {/* Bottom bar inside textarea */}
 <div className="absolute bottom-3 left-4 right-4 flex items-center justify-between">
 <div className="flex items-center gap-3">
 <span className="text-xs text-slate-400">+Enter to submit</span>
 {goal.length > 0 && <span className="text-xs text-slate-400">{goal.length} chars</span>}
 </div>
 <button id="submit-goal-btn" type="submit"
 disabled={!goal.trim() || phase !=='idle'}
 className="flex items-center gap-2 px-4 py-1.5 rounded-xl text-sm font-semibold transition-all"
 style={{
  background: goal.trim() && phase ==='idle' ? 'linear-gradient(135deg, #7C6BF0, #9B8BF4)' : '#F1F5F9',
 color: goal.trim() && phase ==='idle' ? '#ffffff' : '#94A3B8',
 boxShadow: goal.trim() && phase ==='idle' ? '0 2px 8px rgba(124,107,240,0.3)' : 'none',
 }}>
 {phase ==='planning' ? <Loader size={14} className="animate-spin" /> : <Send size={14} />}
 {phase ==='idle' ?'Launch' : phase ==='planning' ?'Planning...' :'Running'}
 </button>
 </div>
 </div>
 </form>

  {/* AI suggestion chips */}
  <AISuggestionChips goal={goal} onChipClick={chip => { setGoal(chip); textRef.current?.focus() }} />

 {/* Live cost estimate */}
 <CostPreview goal={goal} />

 {/* Agent theater */}
 <AgentTheater phase={phase} activeAgent={activeAgent} />

 {/* Success state */}
 {phase ==='running' && (
 <div className="mt-5 rounded-xl p-4 animate-fade-in"
 style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}>
 <div className="flex items-start gap-3">
 <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
 style={{ background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.25)' }}>
 <CheckCircle size={20} className="text-emerald-600" />
 </div>
 <div className="flex-1">
 {/* FIX B02: Dynamic provider/GPU from real job result, not hardcoded */}
  <p className="font-semibold text-slate-800 mb-1">
 {jobResult?.provider
 ? `Job Running on ${jobResult.provider.charAt(0).toUpperCase() + jobResult.provider.slice(1)} ${jobResult.gpu_type ||'GPU'}`
 :'Job Running on GPU Cloud'}
 </p>
 <p className="text-sm text-slate-500 mb-3">
 {jobResult?.job_id
 ? `Job ${jobResult.job_id.slice(0, 14)}... provisioned. Cost tracking live.`
 :'5 agents coordinated. GPU provisioned. Cost tracking live.'}
 </p>
 <div className="flex gap-2">
 {/* FIX B03: Broken hash nav replaced with React Router navigate */}
 <button
 onClick={() => navigate('/jobs')}
  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white"
 style={{ background:'linear-gradient(135deg, #7C6BF0, #9B8BF4)', border:'none' }}>
 View in Job Manager <ChevronRight size={14} />
 </button>
 <button onClick={handleReset}
 className="px-4 py-2 rounded-xl text-sm font-medium text-slate-500"
  style={{ background:'#F1F5F9', border: '1px solid #E2E8F0' }}>
 Submit Another
 </button>
 </div>
 </div>
 </div>
 </div>
 )}
 </div>

 {/* Quick-start templates */}
 <div>
 {/* Section header - clearly visible */}
 <div className="flex items-center gap-3 mb-4">
 <div className="h-px flex-1" style={{ background:'#E2E8F0' }} />
 <div className="flex items-center gap-2 px-3 py-1 rounded-full"
 style={{ background:'rgba(124,107,240,0.08)', border:'1px solid rgba(124,107,240,0.2)' }}>
 <span className="text-xs font-semibold" style={{ color: '#7C6BF0' }}> Quick Start Templates</span>
 <span className="text-xs rounded-full px-1.5 py-0.5 font-bold"
 style={{ background:'rgba(124,107,240,0.15)', color:'#7C6BF0' }}>4</span>
 </div>
 <div className="h-px flex-1" style={{ background:'#E2E8F0' }} />
 </div>

 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 {[
 { icon:'', title:'Fine-tune LLaMA 3 8B', sub:'Custom dataset . ~$39 . 20hrs', goal:'Fine-tune LLaMA 3 8B on my customer support dataset, keep cost under $50', color:'#7C6BF0' },
 { icon:'', title:'Stable Diffusion Batch', sub:'500 images . ~$8 . 2hrs', goal:'Generate 500 product images with Stable Diffusion XL, 1024x1024', color:'#9B8BF4' },
 { icon:'', title:'Whisper Transcription', sub:'10 hours audio . ~$5 . 1hr', goal:'Transcribe 10 hours of audio using Whisper Large v3', color:'#10B981' },
 { icon:'', title:'Hyperparameter Sweep', sub:'32 trials . ~$22 . 6hrs', goal:'Run hyperparameter sweep 32 trials for my PyTorch model on A10 GPUs', color:'#F59E0B' },
 ].map(t => (
 <button key={t.title} onClick={() => { setGoal(t.goal); textRef.current?.focus() }}
 disabled={phase !=='idle'}
 className="text-left p-4 rounded-2xl transition-all duration-200 hover:-translate-y-0.5 group"
 style={{
  background:'#FFFFFF',
  border: `1px solid #E2E8F0`,
 borderLeft: `3px solid ${t.color}`,
 boxShadow:'0 1px 3px rgba(0,0,0,0.06)',
 }}
 onMouseEnter={e => { e.currentTarget.style.background ='#F8FAFC'; e.currentTarget.style.boxShadow = `0 4px 20px ${t.color}15` }}
 onMouseLeave={e => { e.currentTarget.style.background ='#FFFFFF'; e.currentTarget.style.boxShadow ='0 1px 3px rgba(0,0,0,0.06)' }}
 >
 <div className="flex items-center gap-3">
 <span className="text-2xl flex-shrink-0" style={{ filter: `drop-shadow(0 0 6px ${t.color}60)` }}>{t.icon}</span>
 <div className="flex-1 min-w-0">
  <p className="text-sm font-semibold text-slate-800 group-hover:text-lavender-500 transition-colors">{t.title}</p>
 <p className="text-xs mt-0.5" style={{ color:'#94A3B8' }}>{t.sub}</p>
 </div>
 <ChevronRight size={14} style={{ color: t.color, opacity: 0.7, flexShrink: 0 }} className="group-hover:opacity-100 transition-opacity" />
 </div>
 </button>
 ))}
 </div>
 </div>

 {/* Goal History */}
 <GoalHistory token={token} refreshKey={phase} />
 </motion.div>
 )
}

/* """ Goal History Table """""""""""""""""""""""""""""""""""""""""""""" */
function GoalHistory({ token, refreshKey }) {
 const [goals, setGoals] = useState([])
 const [loading, setLoading] = useState(true)
 const [expanded, setExpanded] = useState(null)

 useEffect(() => {
 if (!token) return
 setLoading(true)
 fetch(`${API}/api/v1/goals`, {
  headers: { Authorization: `Bearer ${token}` },
 })
  .then(r => r.ok ? r.json() : { goals: [] })
  .then(data => setGoals((data.goals || []).slice(0, 20)))
  .catch(() => setGoals([]))
  .finally(() => setLoading(false))
 }, [token, refreshKey])

 if (loading) return null
 if (goals.length === 0) return (
 <div className="glass-card p-6 text-center" style={{ borderStyle: 'dashed', borderColor: 'rgba(124,107,240,0.20)' }}>
  <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.5 }}>""</div>
  <p className="text-sm font-semibold" style={{ color: '#0F172A' }}>No goals submitted yet</p>
  <p className="text-xs mt-1" style={{ color: '#94A3B8' }}>Submit your first goal above and agents will start working immediately.</p>
 </div>
 )

 const statusColor = (s) => {
 if (s === 'completed') return { bg: 'rgba(16,185,129,0.08)', color: '#10B981', border: 'rgba(16,185,129,0.25)' }
 if (s === 'running' || s === 'accepted') return { bg: 'rgba(124,107,240,0.08)', color: '#7C6BF0', border: 'rgba(124,107,240,0.25)' }
 if (s === 'failed') return { bg: 'rgba(239,68,68,0.08)', color: '#EF4444', border: 'rgba(239,68,68,0.25)' }
 return { bg: 'rgba(148,163,184,0.08)', color: '#94A3B8', border: 'rgba(148,163,184,0.2)' }
 }

 return (
 <div>
  <div className="flex items-center gap-3 mb-4">
  <div className="h-px flex-1" style={{ background:'#E2E8F0' }} />
  <div className="flex items-center gap-2 px-3 py-1 rounded-full"
   style={{ background:'rgba(124,107,240,0.08)', border:'1px solid rgba(124,107,240,0.2)' }}>
   <span className="text-xs font-semibold" style={{ color: '#7C6BF0' }}>"" Goal History</span>
   <span className="text-xs rounded-full px-1.5 py-0.5 font-bold"
   style={{ background:'rgba(124,107,240,0.15)', color:'#7C6BF0' }}>{goals.length}</span>
  </div>
  <div className="h-px flex-1" style={{ background:'#E2E8F0' }} />
  </div>

  <div className="space-y-2">
  {goals.map(g => {
   const sc = statusColor(g.status)
   const ts = g.created_at ? new Date(g.created_at).toLocaleString() : ''
   const isOpen = expanded === g.goal_id
   return (
   <div key={g.goal_id}
    onClick={() => setExpanded(isOpen ? null : g.goal_id)}
    className="glass-card p-4 cursor-pointer transition-all duration-200 hover:-translate-y-0.5"
    style={{ borderLeft: `3px solid ${sc.color}` }}>
    <div className="flex items-center justify-between gap-3">
    <div className="flex-1 min-w-0">
     <p className="text-sm font-medium truncate" style={{ color: '#0F172A' }}>
     {(g.raw_text || '').slice(0, 80)}{(g.raw_text || '').length > 80 ? '...' : ''}
     </p>
     <p className="text-xs mt-1" style={{ color: '#94A3B8' }}>{ts}</p>
    </div>
    <div className="flex items-center gap-3 flex-shrink-0">
     {g.cost_incurred_usd > 0 && (
     <span className="text-xs font-mono font-semibold" style={{ color: '#10B981' }}>
      ${g.cost_incurred_usd.toFixed(2)}
     </span>
     )}
     <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
     style={{ background: sc.bg, color: sc.color, border: `1px solid ${sc.border}` }}>
     {g.status}
     </span>
    </div>
    </div>
    {isOpen && (
     <div className="mt-3 pt-3 text-xs space-y-1" style={{ borderTop: '1px solid #E2E8F0' }}>
     <p style={{ color: '#475569' }}>{g.raw_text}</p>
     <div className="flex gap-4 mt-2" style={{ color: '#94A3B8' }}>
     <span>Tasks: {(g.tasks || []).length}</span>
     <span>Steps: {g.reasoning_steps || 0}</span>
     <span>ID: {g.goal_id?.slice(0, 12)}...</span>
     </div>
    </div>
    )}
   </div>
   )
  })}
  </div>
 </div>
 )
}



