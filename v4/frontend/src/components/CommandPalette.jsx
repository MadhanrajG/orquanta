import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

/* """ Command Palette + Keyboard Shortcuts """""""""""""""""""""""""""""
 - Cmd/Ctrl+K open command palette
 - ? show keyboard shortcuts help
 - G D go to Dashboard
 - G J go to Jobs
 - G A go to Agents
 - G C go to Costs
 - Escape close any overlay
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""" */

const COMMANDS = [
 { id:'dash', label:'Go to Dashboard', icon:'', shortcut:'G D', action:'nav://' },
 { id:'goals', label:'Submit New Goal', icon:'', shortcut:'N', action:'nav://goals' },
 { id:'jobs', label:'View All Jobs', icon:'', shortcut:'G J', action:'nav://jobs' },
 { id:'agents', label:'Agent Monitor', icon:'', shortcut:'G A', action:'nav://agents' },
 { id:'costs', label:'Cost Analytics', icon:'', shortcut:'G C', action:'nav://costs' },
 { id:'audit', label:'Audit Log', icon:'', shortcut:'G L', action:'nav://audit' },
 { id:'assistant', label:'Open AI Assistant', icon:'', shortcut:'A', action:'assistant' },
 { id:'estop', label:'Emergency Stop ALL', icon:'', shortcut:'!', action:'estop', danger: true },
 { id:'prices', label:'Compare GPU Prices', icon:'', shortcut:'P', action:'prices' },
 { id:'help', label:'Keyboard Shortcuts', icon:'', shortcut:'?', action:'help' },
 { id:'refresh', label:'Refresh Dashboard', icon:'', shortcut:'R', action:'refresh' },
 { id:'theme', label:'Toggle Compact Mode', icon:'', shortcut:'T', action:'theme' },
]

const SHORTCUT_HELP = [
 {
 group:'Navigation', items: [
 { keys: ['Cmd','K'], desc:'Open command palette' },
 { keys: ['?'], desc:'Show keyboard shortcuts' },
 { keys: ['G','D'], desc:'Go to Dashboard' },
 { keys: ['G','J'], desc:'Go to Jobs' },
 { keys: ['G','A'], desc:'Go to Agents' },
 { keys: ['G','C'], desc:'Go to Cost Analytics' },
 { keys: ['G','L'], desc:'Go to Audit Log' },
 ]
 },
 {
 group:'Actions', items: [
 { keys: ['N'], desc:'New goal submission' },
 { keys: ['A'], desc:'Open AI assistant' },
 { keys: ['P'], desc:'Compare GPU prices' },
 { keys: ['R'], desc:'Refresh current view' },
 { keys: ['T'], desc:'Toggle compact mode' },
 ]
 },
 {
 group:'Emergency', items: [
 { keys: ['!'], desc:'Emergency stop all instances', danger: true },
 ]
 },
 {
 group:'Global', items: [
 { keys: ['Esc'], desc:'Close overlays / cancel' },
 { keys: ['',''], desc:'Navigate palette results' },
 { keys: [''], desc:'Execute selected command' },
 ]
 },
]

function Kbd({ children }) {
 return (
 <kbd className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono"
  style={{ background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.1)', color:'#CBD5E1' }}>
 {children}
 </kbd>
 )
}

/* """ Keyboard Shortcuts Modal """"""""""""""""""""""""""""""""""""""""""" */
function ShortcutsModal({ onClose }) {
 return (
  <motion.div className="fixed inset-0 z-[100] flex items-center justify-center p-4" onClick={onClose}
  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
  <div className="absolute inset-0" style={{ background:'rgba(0,0,0,0.75)', backdropFilter:'blur(8px)' }} />
  <motion.div className="relative w-full max-w-xl rounded-2xl overflow-hidden"
  initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
  transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
  style={{ background:'#0B0E18', border:'1px solid rgba(255,255,255,0.06)', boxShadow:'0 8px 40px rgba(0,0,0,0.5), 0 32px 64px rgba(0,0,0,0.3)' }}
  onClick={e => e.stopPropagation()}>
  <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor:'rgba(255,255,255,0.06)' }}>
  <div className="flex items-center gap-2">
  <span className="text-lg"></span>
  <h3 className="font-semibold text-slate-100">Keyboard Shortcuts</h3>
  </div>
  <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-100"><Kbd>Esc</Kbd></button>
  </div>
  <div className="p-6 grid grid-cols-2 gap-6 max-h-96 overflow-y-auto">
  {SHORTCUT_HELP.map(group => (
  <div key={group.group}>
  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">{group.group}</div>
  <div className="space-y-2">
  {group.items.map((item, i) => (
  <div key={i} className="flex items-center justify-between gap-4">
  <span className="text-xs text-slate-400 flex-1" style={item.danger ? { color:'#F87171' } : {}}>{item.desc}</span>
  <div className="flex gap-1 shrink-0">
  {item.keys.map((k, j) => <Kbd key={j}>{k}</Kbd>)}
  </div>
  </div>
  ))}
  </div>
  </div>
  ))}
  </div>
  </motion.div>
  </motion.div>
  )
}

/* """ Cmd+K Command Palette """""""""""""""""""""""""""""""""""""""""""""" */
function CommandPalette({ onClose, onNavigate }) {
 const [query, setQuery] = useState('')
 const [selected, setSelected] = useState(0)
 const inputRef = useRef(null)

 const filtered = COMMANDS.filter(c =>
 c.label.toLowerCase().includes(query.toLowerCase()) ||
 c.id.includes(query.toLowerCase())
 )

 useEffect(() => { setTimeout(() => inputRef.current?.focus(), 50) }, [])
 useEffect(() => { setSelected(0) }, [query])

 const execute = useCallback((cmd) => {
 onClose()
 if (cmd.action.startsWith('nav://')) {
 const path = cmd.action.replace('nav://','') ||'/'
 onNavigate(path ||'/')
 } else if (cmd.action ==='assistant') {
 document.getElementById('assistant-toggle')?.click()
 } else if (cmd.action ==='refresh') {
 window.location.reload()
 } else if (cmd.action ==='estop') {
 if (window.confirm('Emergency stop ALL instances? This will terminate all running GPU jobs.')) {
 fetch('/emergency-stop', { method:'POST' }).catch(() => { })
 alert('Emergency stop signal sent. All instances will terminate within 30 seconds.')
 }
 }
 }, [onClose, onNavigate])

 const handleKey = (e) => {
 if (e.key ==='ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)) }
 if (e.key ==='ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
 if (e.key ==='Enter' && filtered[selected]) execute(filtered[selected])
 if (e.key ==='Escape') onClose()
 }

 return (
  <motion.div className="fixed inset-0 z-[100] flex items-start justify-center pt-24 px-4" onClick={onClose}
  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
  <div className="absolute inset-0" style={{ background:'rgba(0,0,0,0.75)', backdropFilter:'blur(8px)' }} />
  <motion.div className="relative w-full max-w-lg rounded-2xl overflow-hidden"
  initial={{ opacity: 0, y: -20, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -20, scale: 0.96 }}
  transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
  style={{ background:'#0B0E18', border:'1px solid rgba(255,255,255,0.06)', boxShadow:'0 8px 40px rgba(0,0,0,0.5), 0 32px 64px rgba(0,0,0,0.3)' }}
  onClick={e => e.stopPropagation()}>
  {/* Input */}
  <div className="flex items-center gap-3 px-4 py-3.5 border-b" style={{ borderColor:'rgba(255,255,255,0.06)' }}>
  <span className="text-slate-500"></span>
  <input ref={inputRef} id="palette-input"
  value={query} onChange={e => setQuery(e.target.value)} onKeyDown={handleKey}
  placeholder="Search commands, pages, actions..."
  className="flex-1 bg-transparent text-slate-100 text-sm outline-none placeholder-slate-500"
  />
  {query && <button onClick={() => setQuery('')} className="text-xs text-slate-400 hover:text-slate-100">Clear</button>}
  </div>

  {/* Results */}
  <motion.div className="max-h-80 overflow-y-auto py-2"
  initial="hidden" animate="visible" variants={{ visible: { transition: { staggerChildren: 0.03 } } }}>
  {filtered.length === 0 ? (
  <div className="text-center py-8 text-slate-500 text-sm">No commands found</div>
  ) : (
  filtered.map((cmd, i) => (
  <motion.button key={cmd.id} id={`palette-cmd-${cmd.id}`}
  variants={{ hidden: { opacity: 0, x: -8 }, visible: { opacity: 1, x: 0 } }}
  className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-all"
  style={{
  background: i === selected ?'rgba(0,145,255,0.1)' :'transparent',
  borderLeft: i === selected ?'2px solid #0091FF' :'2px solid transparent',
  }}
  onClick={() => execute(cmd)}
  onMouseEnter={() => setSelected(i)}>
  <span className="text-base w-6 text-center">{cmd.icon}</span>
  <span className="flex-1 text-sm" style={{ color: cmd.danger ?'#F87171' : i === selected ?'#E2E8F0' :'#94A3B8' }}>
  {cmd.label}
  </span>
  <div className="flex gap-1 shrink-0">
  {cmd.shortcut.split('').map((k, j) => <Kbd key={j}>{k}</Kbd>)}
  </div>
  </motion.button>
  ))
  )}
  </motion.div>
  <div className="px-4 py-2.5 border-t flex items-center gap-4 text-xs text-slate-500" style={{ borderColor:'rgba(255,255,255,0.06)' }}>
  <span><Kbd></Kbd> navigate</span>
  <span><Kbd></Kbd> run</span>
  <span><Kbd>Esc</Kbd> close</span>
  </div>
  </motion.div>
  </motion.div>
  )
}

/* """ Main Hook + Provider """""""""""""""""""""""""""""""""""""""""""""" */

export function useCommandPalette(navigate) {
 const [paletteOpen, setPaletteOpen] = useState(false)
 const [shortcutsOpen, setShortcutsOpen] = useState(false)
 const gBuffer = useRef('')

 useEffect(() => {
 const handler = (e) => {
 const tag = document.activeElement?.tagName
 const isInput = ['INPUT','TEXTAREA','SELECT'].includes(tag)

 // Cmd/Ctrl+K
 if ((e.metaKey || e.ctrlKey) && e.key ==='k') {
 e.preventDefault(); setPaletteOpen(p => !p); return
 }
 if (isInput) return

 // Escape
 if (e.key ==='Escape') { setPaletteOpen(false); setShortcutsOpen(false); return }
 // ?
 if (e.key ==='?') { setShortcutsOpen(p => !p); return }
 // N - new goal
 if (e.key ==='n' || e.key ==='N') { navigate?.('/goals'); return }
 // A - assistant
 if (e.key ==='a' || e.key ==='A') { document.getElementById('assistant-toggle')?.click(); return }

 // G-prefixed two-key shortcuts
 if (e.key ==='g' || e.key ==='G') { gBuffer.current ='g'; return }
 if (gBuffer.current ==='g') {
 gBuffer.current =''
 if (e.key ==='d' || e.key ==='D') navigate?.('/')
 else if (e.key ==='j' || e.key ==='J') navigate?.('/jobs')
 else if (e.key ==='a' || e.key ==='A') navigate?.('/agents')
 else if (e.key ==='c' || e.key ==='C') navigate?.('/costs')
 else if (e.key ==='l' || e.key ==='L') navigate?.('/audit')
 }
 }
 window.addEventListener('keydown', handler)
 return () => window.removeEventListener('keydown', handler)
 }, [navigate])

 return { paletteOpen, setPaletteOpen, shortcutsOpen, setShortcutsOpen }
}

export { CommandPalette, ShortcutsModal, Kbd }


