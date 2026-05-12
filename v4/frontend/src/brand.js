/**
 * OrQuanta Brand Constants
 * ========================
 * Single source of truth for all brand colors, typography, and identity.
 * Import this everywhere you need brand values - never hard-code colors.
 *
 * Usage:
 * import { BRAND, COLORS, GRADIENTS } from'./brand'
 */

export const BRAND = {
 name: "OrQuanta",
 fullName: "OrQuanta Agentic",
 version: "1.0.0",
 tagline: "Orchestrate. Optimize. Evolve.",
 taglineParts: ["Orchestrate.", "Optimize.", "Evolve."],
 description:
 "The first Agentic AI Cloud GPU platform that autonomously orchestrates, " +
 "optimizes and heals your GPU workloads across AWS, GCP, Azure and CoreWeave.",
 email: "hello@orquanta.com",
 website: "https://orquanta.com",
 apiBase: "",
 docsUrl: "https://docs.orquanta.com",
 githubUrl: "https://github.com/orquanta",
 discordUrl: "https://discord.gg/orquanta",
 twitterUrl: "https://twitter.com/OrQuantaAI",
};

export const COLORS = {
 // ─── Brand Colors ───────────────────────────────────────────
 primary: "#0091FF", // Quantum Blue - CTAs, links, active states
 secondary: "#7B2FFF", // Deep Purple - gradients, highlights

 // ─── Backgrounds ────────────────────────────────────────────
 background: "#FFFFFF", // White - page background
 surface: "#F8FAFC", // Light Gray - cards, modals
 surfaceAlt: "#F1F5F9", // Slightly darker surface
 border: "#E2E8F0", // Card borders, dividers

 // ─── Semantic Colors ─────────────────────────────────────────
 success: "#10B981", // Emerald - job complete, healthy status
 warning: "#F59E0B", // Amber - cost alerts, spend warnings
 error: "#EF4444", // Alert Red - failures, critical
 info: "#0091FF", // Same as primary for info banners

 // ─── Text ────────────────────────────────────────────────────
 textPrimary: "#0F172A",
 textSecondary: "#475569",
 textMuted: "#94A3B8",
 textInverse: "#FFFFFF",

 // ─── GPU Provider Colors (for charts) ────────────────────────
 aws: "#FF9900",
 gcp: "#4285F4",
 azure: "#0078D4",
 coreweave: "#0091FF",
};

export const GRADIENTS = {
 primary: "linear-gradient(135deg, #0091FF 0%, #7B2FFF 100%)",
 primaryReverse: "linear-gradient(135deg, #7B2FFF 0%, #0091FF 100%)",
 hero: "linear-gradient(135deg, #0091FF 0%, #7B2FFF 50%, #F8FAFC 100%)",
 card: "linear-gradient(145deg, #FFFFFF 0%, #F8FAFC 100%)",
 success: "linear-gradient(135deg, #10B981 0%, #0091FF 100%)",
 danger: "linear-gradient(135deg, #EF4444 0%, #F59E0B 100%)",
 surface: "linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 100%)",
};

export const SHADOWS = {
 primary: "0 4px 24px rgba(0, 145, 255, 0.12)",
 primaryStrong: "0 8px 40px rgba(0, 145, 255, 0.18)",
 purple: "0 4px 24px rgba(123, 47, 255, 0.12)",
 card: "0 1px 3px rgba(0, 0, 0, 0.08), 0 4px 12px rgba(0, 0, 0, 0.04)",
 cardHover: "0 4px 24px rgba(0, 145, 255, 0.08)",
 success: "0 4px 16px rgba(16, 185, 129, 0.12)",
 error: "0 4px 16px rgba(239, 68, 68, 0.12)",
};

export const TYPOGRAPHY = {
 fontDisplay: "'Space Grotesk', sans-serif",
 fontBody: "'Inter', sans-serif",
 fontCode: "'JetBrains Mono', monospace",

 sizes: {
 xs: "0.75rem", // 12px
 sm: "0.875rem", // 14px
 base: "1rem", // 16px
 lg: "1.125rem", // 18px
 xl: "1.25rem", // 20px
 "2xl": "1.5rem", // 24px
 "3xl": "1.875rem", // 30px
 "4xl": "2.25rem", // 36px
 "5xl": "3rem", // 48px
 "6xl": "3.75rem", // 60px
 "7xl": "4.5rem", // 72px
 },

 weights: {
 normal: 400,
 medium: 500,
 semibold: 600,
 bold: 700,
 extrabold: 800,
 },
};

export const SPACING = {
 xs: "0.25rem", // 4px
 sm: "0.5rem", // 8px
 md: "1rem", // 16px
 lg: "1.5rem", // 24px
 xl: "2rem", // 32px
 "2xl": "3rem", // 48px
 "3xl": "4rem", // 64px
 "4xl": "6rem", // 96px
 "5xl": "8rem", // 128px
};

export const BORDER_RADIUS = {
 sm: "0.375rem", // 6px
 md: "0.5rem", // 8px
 lg: "0.75rem", // 12px
 xl: "1rem", // 16px
 "2xl": "1.5rem", // 24px
 full: "9999px",
};

export const ANIMATION = {
 fast: "150ms ease",
 normal: "250ms ease",
 slow: "400ms ease",
 spring: "300ms cubic-bezier(0.34, 1.56, 0.64, 1)",
 pulse: "2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
};

export const BREAKPOINTS = {
 sm: "640px",
 md: "768px",
 lg: "1024px",
 xl: "1280px",
 "2xl": "1536px",
};

// Agent display names and colors
export const AGENTS = {
 master_orchestrator: { name: "OrMind Orchestrator", color: COLORS.primary, icon: "" },
 scheduler_agent: { name: "Scheduler", color: COLORS.secondary, icon: "" },
 cost_optimizer_agent: { name: "Cost Optimizer", color: "#00FF88", icon: "" },
 healing_agent: { name: "Healing Agent", color: "#FFB800", icon: "" },
 audit_agent: { name: "Audit Agent", color: "#8892A4", icon: "" },
};

// GPU provider display config
export const PROVIDERS = {
 aws: { name: "AWS", color: COLORS.aws, logo: "aws-logo.svg" },
 gcp: { name: "GCP", color: COLORS.gcp, logo: "gcp-logo.svg" },
 azure: { name: "Azure", color: COLORS.azure, logo: "azure-logo.svg" },
 coreweave: { name: "CoreWeave", color: COLORS.coreweave, logo: "coreweave-logo.svg" },
};

export const GPU_TYPES = ["H100", "A100", "A10G", "V100", "T4", "L4", "L40S"];

// Plan definitions (mirror v4/billing/stripe_integration.py)
export const PLANS = {
 starter: {
 name: "Starter",
 price: 99,
 gpu_spend_limit: 5000,
 max_agents: 2,
 color: COLORS.primary,
 popular: false,
 },
 pro: {
 name: "Pro",
 price: 499,
 gpu_spend_limit: 30000,
 max_agents: 10,
 color: COLORS.secondary,
 popular: true,
 },
 enterprise: {
 name: "Enterprise",
 price: null,
 gpu_spend_limit: null,
 max_agents: null,
 color: COLORS.success,
 popular: false,
 },
};

export default BRAND;
