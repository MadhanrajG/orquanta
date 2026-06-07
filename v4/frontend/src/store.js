import { create } from 'zustand'

export const useAppStore = create((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  
  commandPaletteOpen: false,
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
  
  notifications: [],
  addNotification: (n) => set((s) => ({ notifications: [n, ...s.notifications].slice(0, 20) })),
  clearNotifications: () => set({ notifications: [] }),
}))

export const useMetricsStore = create((set) => ({
  health: null,
  gpuMetrics: null,
  costData: null,
  agentStates: {},
  
  setHealth: (health) => set({ health }),
  setGpuMetrics: (gpuMetrics) => set({ gpuMetrics }),
  setCostData: (costData) => set({ costData }),
  setAgentState: (agentId, state) => set((s) => ({
    agentStates: { ...s.agentStates, [agentId]: state }
  })),
}))
