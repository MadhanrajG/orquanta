/* ─────────────────────────────────────────────────────────────────
   Skeleton.jsx  –  shimmer loading skeletons for OrQuanta
   ───────────────────────────────────────────────────────────────── */
import { motion } from 'framer-motion'

const shimmer = {
  animate: {
    backgroundPosition: ['200% 0', '-200% 0'],
  },
  transition: {
    duration: 1.6,
    repeat: Infinity,
    ease: 'linear',
  },
}

const baseStyle = {
  borderRadius: 8,
  background: 'linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.10) 50%, rgba(255,255,255,0.04) 75%)',
  backgroundSize: '400% 100%',
}

function Bone({ w = '100%', h = 16, style = {} }) {
  return (
    <motion.div
      animate={shimmer.animate}
      transition={shimmer.transition}
      style={{ width: w, height: h, ...baseStyle, ...style }}
    />
  )
}

/** Single stat card skeleton */
export function SkeletonStat() {
  return (
    <div className="glass-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Bone w={80} h={12} />
        <Bone w={28} h={28} style={{ borderRadius: '50%' }} />
      </div>
      <Bone w={120} h={28} />
      <Bone w={90} h={10} />
    </div>
  )
}

/** Grid of stat card skeletons */
export function SkeletonStatGrid({ cols = 4 }) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-${cols} gap-4`}>
      {Array.from({ length: cols }).map((_, i) => <SkeletonStat key={i} />)}
    </div>
  )
}

/** Table row skeleton */
export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="glass-card p-4 overflow-hidden">
      {/* Header */}
      <div className="flex gap-4 mb-4 pb-3 border-b border-white/5">
        {Array.from({ length: cols }).map((_, i) => (
          <Bone key={i} w={`${100 / cols}%`} h={12} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 py-3 border-b border-white/5">
          {Array.from({ length: cols }).map((_, c) => (
            <Bone key={c} w={`${100 / cols}%`} h={12}
              style={{ opacity: 1 - r * 0.12 }} />
          ))}
        </div>
      ))}
    </div>
  )
}

/** Card skeleton with title + body lines */
export function SkeletonCard({ rows = 3, style = {} }) {
  return (
    <div className="glass-card p-5 flex flex-col gap-3" style={style}>
      <Bone w="60%" h={16} />
      <Bone w="40%" h={10} />
      <div className="mt-2 flex flex-col gap-2">
        {Array.from({ length: rows }).map((_, i) => (
          <Bone key={i} w={`${100 - i * 10}%`} h={11} />
        ))}
      </div>
    </div>
  )
}

/** Full page loading state — centered spinner + message */
export function SkeletonPage({ message = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 0.9, repeat: Infinity, ease: 'linear' }}
        style={{
          width: 36, height: 36, borderRadius: '50%',
          border: '3px solid rgba(123,47,255,0.15)',
          borderTopColor: '#7B2FFF',
        }}
      />
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  )
}

/** Chart area skeleton */
export function SkeletonChart({ h = 180 }) {
  return (
    <div className="glass-card p-4">
      <Bone w="40%" h={14} style={{ marginBottom: 16 }} />
      <Bone w="100%" h={h} style={{ borderRadius: 12 }} />
    </div>
  )
}
