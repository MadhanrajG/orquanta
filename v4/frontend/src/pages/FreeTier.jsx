import { useState, useEffect } from'react'
import { Zap, Download, ExternalLink, CheckCircle, Clock, Cpu, DollarSign, AlertTriangle } from'lucide-react'

const API =''

const TEMPLATES = [
 { label:'Fine-tune LLaMA 3 8B', goal:'Fine-tune LLaMA 3 8B on my customer support dataset using LoRA, keep cost under $0' },
 { label:'Stable Diffusion XL', goal:'Generate 10 photorealistic product images using Stable Diffusion XL' },
 { label:'Whisper Transcription', goal:'Transcribe audio files using Whisper large-v3 model' },
 { label:'Text Embeddings', goal:'Generate sentence embeddings for 50,000 documents using BGE-large' },
 { label:'Mistral 7B Inference', goal:'Run batch inference with Mistral 7B Instruct on 1000 prompts' },
 { label:'Data Preprocessing', goal:'Tokenize and preprocess a CSV dataset for training, output to JSONL' },
]

const FREE_OPTIONS = [
 {
 id:'colab', icon:'', name:'Google Colab',
 gpu:'T4 16GB', hours:'~12 hrs/day',
 desc:'Generate a notebook Open in Colab Run All. Zero setup.',
 badge:'Most Popular', badgeColor:'#F59E0B', cost:'$0.00',
 },
 {
 id:'kaggle', icon:'', name:'Kaggle Kernels',
 gpu:'T4 / P100 16GB', hours:'30 hrs/week',
 desc:'Full automation. OrQuanta submits & monitors via Kaggle API.',
 badge:'Most Automated', badgeColor:'#0091FF', cost:'$0.00',
 },
 {
 id:'lambda', icon:'', name:'Lambda Labs',
 gpu:'A10 / A100', hours:'$10 free credits',
 desc:'New users get $10 credits. Real A100 GPU, full API control.',
 badge:'Best Hardware', badgeColor:'#10B981', cost:'$0 to start',
 },
]

export default function FreeTierPage() {
 const [goal, setGoal] = useState('')
 const [loading, setLoading] = useState(false)
 const [result, setResult] = useState(null)
 const [error, setError] = useState('')
 const [activeTab, setActiveTab] = useState('generate')

 const generateNotebook = async () => {
 if (!goal.trim() || goal.trim().length < 5) {
 setError('Please describe your GPU task (at least 5 characters)')
 return
 }
 setLoading(true); setError(''); setResult(null)
 try {
 const token = localStorage.getItem('orquanta_token') ||''
 const res = await fetch(`${API}/api/v1/free/notebook`, {
 method:'POST',
 headers: {'Content-Type':'application/json', Authorization: `Bearer ${token}` },
 body: JSON.stringify({ goal: goal.trim() }),
 })
 if (!res.ok) {
 const err = await res.json().catch(() => ({}))
 throw new Error(err.detail ||'Generation failed')
 }
 setResult(await res.json())
 } catch (e) {
 setError(e.message)
 } finally {
 setLoading(false)
 }
 }

 const downloadNotebook = (jobId) => {
 const token = localStorage.getItem('orquanta_token') ||''
 window.open(`${API}/api/v1/free/notebook/download/${jobId}`,'_blank')
 }

 return (
 <div className="space-y-6 animate-fade-in">
 {/* Header */}
 <div>
 <h1 className="text-2xl font-bold text-gray-900" style={{ display:'flex', alignItems:'center', gap: 10 }}>
 <span style={{ fontSize: 28 }}></span> Free GPU Tier
 </h1>
 <p className="text-slate-400 text-sm mt-1">
 Run GPU workloads at $0 - Google Colab . Kaggle . Lambda Labs free credits
 </p>
 </div>

 {/* Free options strip */}
 <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
 {FREE_OPTIONS.map(opt => (
 <div key={opt.id} className="glass-card p-5" style={{ position:'relative' }}>
 <div style={{
 position:'absolute', top: 12, right: 12,
 background: `${opt.badgeColor}18`, color: opt.badgeColor,
 border: `1px solid ${opt.badgeColor}40`, borderRadius: 999,
 fontSize: 11, fontWeight: 700, padding:'2px 10px'
 }}>
 {opt.badge}
 </div>
 <div style={{ fontSize: 28, marginBottom: 8 }}>{opt.icon}</div>
 <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)', marginBottom: 4 }}>{opt.name}</div>
 <div style={{ display:'flex', gap: 12, marginBottom: 8 }}>
 <span style={{ fontSize: 12, color:'#0091FF' }}> {opt.gpu}</span>
 <span style={{ fontSize: 12, color:'#10B981' }}> {opt.hours}</span>
 </div>
 <p style={{ fontSize: 13, color:'var(--text-muted)', lineHeight: 1.5, marginBottom: 10 }}>{opt.desc}</p>
 <div style={{ fontWeight: 700, color:'#10B981', fontSize: 15 }}>{opt.cost}</div>
 </div>
 ))}
 </div>

 {/* Main Generator Card */}
 <div className="glass-card p-6">
 <div style={{ display:'flex', gap: 8, marginBottom: 24 }}>
 {[['generate',' Generate Notebook'], ['kaggle',' Auto-Run on Kaggle']].map(([tab, label]) => (
 <button key={tab} onClick={() => setActiveTab(tab)} style={{
 padding:'8px 18px', borderRadius: 8, border:'none', cursor:'pointer',
 fontSize: 13, fontWeight: 600, transition:'all 0.2s',
 background: activeTab === tab ?'linear-gradient(135deg,#3a52eb,#5a72fb)' :'rgba(0,0,0,0.04)',
 color: activeTab === tab ?'#fff' :'var(--text-muted)',
 }}>{label}</button>
 ))}
 </div>

 {activeTab ==='generate' && (
 <div>
 <h2 style={{ fontWeight: 700, fontSize: 18, color: 'var(--text-primary)', marginBottom: 6 }}>
 Generate a Free GPU Notebook
 </h2>
 <p style={{ color:'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
 Describe your job in plain English OrQuanta generates a complete, ready-to-run notebook.
 Open in Colab or Kaggle - free T4 GPU starts immediately.
 </p>

 {/* Quick templates */}
 <div style={{ display:'flex', gap: 8, flexWrap:'wrap', marginBottom: 16 }}>
 {TEMPLATES.map(t => (
 <button key={t.label} onClick={() => setGoal(t.goal)}
 style={{
 padding:'5px 12px', borderRadius: 20, border:'1px solid rgba(0,145,255,0.25)',
 background:'rgba(0,145,255,0.06)', color:'#7a9bfa', fontSize: 12,
 cursor:'pointer', fontWeight: 500
 }}>
 {t.label}
 </button>
 ))}
 </div>

 <textarea
 value={goal}
 onChange={e => setGoal(e.target.value)}
 placeholder="e.g. Fine-tune LLaMA 3 8B on my product FAQ dataset using LoRA..."
 style={{
 width:'100%', minHeight: 100, background:'rgba(0,0,0,0.3)',
 border:'1px solid rgba(0,145,255,0.2)', borderRadius: 8,
 color:'#E8EAF6', fontSize: 14, padding: 14, marginBottom: 16,
 fontFamily:'Inter, sans-serif', resize:'vertical', outline:'none',
 boxSizing:'border-box'
 }}
 />

 {error && (
 <div className="alert alert-error" style={{ marginBottom: 16 }}>
 <AlertTriangle size={14} />
 <span>{error}</span>
 </div>
 )}

 <button onClick={generateNotebook} disabled={loading}
 className="btn btn-primary"
 style={{ padding:'12px 28px', fontSize: 15, fontWeight: 700 }}>
 {loading
 ? <><span className="spinner" style={{ width: 16, height: 16 }} /> Generating notebook...</>
 :' Generate Free GPU Notebook '
 }
 </button>

 {/* Result */}
 {result && (
 <div style={{
 marginTop: 24, padding: 20, background:'rgba(0,255,136,0.06)',
 border:'1px solid rgba(0,255,136,0.2)', borderRadius: 12
 }}>
 <div style={{ display:'flex', alignItems:'center', gap: 10, marginBottom: 16 }}>
 <CheckCircle size={20} color="#10B981" />
 <span style={{ fontWeight: 700, color:'#10B981', fontSize: 16 }}>
 Notebook Ready - {result.cell_count} cells generated
 </span>
 <span style={{
 marginLeft:'auto', fontSize: 13, color:'var(--text-muted)',
 background:'rgba(0,255,136,0.1)', border:'1px solid rgba(0,255,136,0.2)',
 borderRadius: 6, padding:'2px 10px'
 }}>
 Task: {result.task_type?.replace('_','')}
 </span>
 </div>

 <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap: 12, marginBottom: 20 }}>
 {[
 ['Model', result.model_id?.split('/')[1] || result.model_id,'#0091FF'],
 ['Cost','$0.00 (Free!)','#10B981'],
 ['GPU','T4 16GB (Colab/Kaggle)','#fff'],
 ['File', result.filename,'#A78BFA'],
 ].map(([label, val, color]) => (
 <div key={label} style={{ background:'rgba(0,0,0,0.3)', borderRadius: 8, padding:'10px 14px' }}>
 <div style={{ fontSize: 11, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing: 1 }}>{label}</div>
 <div style={{ color, fontWeight: 700, marginTop: 2, fontSize: 13 }}>{val}</div>
 </div>
 ))}
 </div>

 <div style={{ display:'flex', gap: 10, flexWrap:'wrap', marginBottom: 20 }}>
 <button onClick={() => downloadNotebook(result.job_id)}
 style={{
 display:'flex', alignItems:'center', gap: 8, padding:'10px 20px',
 background:'linear-gradient(135deg,#3a52eb,#5a72fb)', color:'#fff',
 border:'none', borderRadius: 8, cursor:'pointer', fontWeight: 700, fontSize: 14
 }}>
 <Download size={15} /> Download .ipynb
 </button>
 <a href="https://colab.research.google.com" target="_blank" rel="noopener noreferrer"
 style={{
 display:'flex', alignItems:'center', gap: 8, padding:'10px 20px',
 background:'rgba(255,183,0,0.12)', color:'#F59E0B',
 border:'1px solid rgba(255,183,0,0.3)', borderRadius: 8, textDecoration:'none',
 fontWeight: 700, fontSize: 14
 }}>
 <ExternalLink size={15} /> Open Colab 
 </a>
 <a href="https://www.kaggle.com/code" target="_blank" rel="noopener noreferrer"
 style={{
 display:'flex', alignItems:'center', gap: 8, padding:'10px 20px',
 background:'rgba(0,145,255,0.08)', color:'#0091FF',
 border:'1px solid rgba(0,145,255,0.25)', borderRadius: 8, textDecoration:'none',
 fontWeight: 700, fontSize: 14
 }}>
 <ExternalLink size={15} /> Open Kaggle 
 </a>
 </div>

 <div style={{ background:'rgba(0,0,0,0.3)', borderRadius: 8, padding: 14 }}>
 <div style={{ fontSize: 12, fontWeight: 700, color:'var(--text-muted)', marginBottom: 8 }}>
 HOW TO RUN (3 steps):
 </div>
 {result.instructions?.map((step, i) => (
 <div key={i} style={{ fontSize: 13, color:'#E8EAF6', marginBottom: 4 }}>
 {step}
 </div>
 ))}
 </div>
 </div>
 )}
 </div>
 )}

 {activeTab ==='kaggle' && (
 <div>
 <h2 style={{ fontWeight: 700, fontSize: 18, color: 'var(--text-primary)', marginBottom: 6 }}>
 Auto-Run on Kaggle (Full Automation)
 </h2>
 <p style={{ color:'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
 OrQuanta submits, monitors, and retrieves your job from Kaggle's free GPU automatically.
 30 hrs/week of T4/P100 GPU - zero cost.
 </p>
 <div style={{
 background:'rgba(255,183,0,0.06)', border:'1px solid rgba(255,183,0,0.2)',
 borderRadius: 8, padding: 16, marginBottom: 20
 }}>
 <div style={{ fontWeight: 700, color:'#F59E0B', marginBottom: 8 }}> Setup (5 minutes once):</div>
 {[
'1. Sign up at kaggle.com (free)',
'2. Go to kaggle.com/settings/account scroll to API section',
'3. Click "Create New API Token" downloads kaggle.json',
'4. Open kaggle.json copy your username and key below',
'5. OrQuanta handles everything else automatically',
 ].map((s, i) => (
 <div key={i} style={{ fontSize: 13, color:'#E8EAF6', marginBottom: 4 }}>{s}</div>
 ))}
 </div>
 <div style={{ display:'flex', gap: 12, flexDirection:'column', maxWidth: 480 }}>
 <a href="https://www.kaggle.com/account/login" target="_blank" rel="noopener noreferrer"
 className="btn btn-primary" style={{ textAlign:'center', textDecoration:'none', padding:'12px 24px' }}>
 Sign Up for Kaggle Free 
 </a>
 <a href="https://www.kaggle.com/settings/account" target="_blank" rel="noopener noreferrer"
 style={{
 textAlign:'center', padding:'12px 24px', borderRadius: 8, border:'1px solid rgba(0,145,255,0.3)',
 color:'#0091FF', textDecoration:'none', fontWeight: 600, fontSize: 14
 }}>
 Get Kaggle API Token 
 </a>
 </div>
 <p style={{ marginTop: 20, fontSize: 13, color:'var(--text-muted)' }}>
 Once you have your API key, come back here and paste it in OrQuanta will submit your first free job in &lt;30 seconds.
 </p>
 </div>
 )}
 </div>
 </div>
 )
}


