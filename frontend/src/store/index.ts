import { create } from 'zustand'
import { persist, devtools, createJSONStorage } from 'zustand/middleware'

type Mode = 'backtest' | 'paper' | 'semi_auto' | 'full_auto' | 'halted'
type Theme = 'dark' | 'light'

export interface LLMModelInfo {
  key: string
  model_id: string
  label: string
  active: boolean
  economy_default: boolean
}

export interface LLMModelRegistry {
  selection: string
  active_model_ids: string[]
  economy_model: string
  invalid: string[]
  models: LLMModelInfo[]
}

interface AppState {
  mode: Mode
  theme: Theme
  killswitchActive: boolean
  token: string
  isAuthenticated: boolean
  // Canonical comma-separated model keys, e.g. "glm52,gptoss". Never "all" in the UI.
  llmModels: string
  llmModelRegistry: LLMModelRegistry | null
  setMode: (mode: Mode) => void
  setTheme: (theme: Theme) => void
  setKillswitch: (active: boolean) => void
  setToken: (token: string) => void
  logout: () => void
  setLlmModels: (models: string) => void
  setLlmModelRegistry: (registry: LLMModelRegistry | null) => void
}

export const useStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'paper',
        theme: 'dark',
        killswitchActive: false,
        token: '',
        isAuthenticated: false,
        llmModels: 'all',
        llmModelRegistry: null,
        setMode: (mode) => set({ mode }),
        setTheme: (theme) => set({ theme }),
        setKillswitch: (killswitchActive) => set({ killswitchActive }),
        setToken: (token) => set({ token, isAuthenticated: !!token }),
        logout: () => set({ token: '', isAuthenticated: false }),
        setLlmModels: (llmModels) => set({ llmModels }),
        setLlmModelRegistry: (llmModelRegistry) => set({ llmModelRegistry }),
      }),
      {
        name: 'alembic-store',
        storage: createJSONStorage(() => sessionStorage),
        partialize: (s) => ({ token: s.token, isAuthenticated: s.isAuthenticated, mode: s.mode, theme: s.theme }),
      }
    ),
    { name: 'AlembicStore' }
  )
)
