import { create } from 'zustand'
import { persist, devtools, createJSONStorage } from 'zustand/middleware'
import type { Mode } from '@/types/system'

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
        storage: createJSONStorage(() => localStorage),
        // B5: il token NON è più persistito. sessionStorage era accessibile
        // a qualsiasi script in caso di XSS, quindi il JWT poteva essere
        // esfiltato. Ora il token vive solo in memoria: si riloggia al
        // prossimo refresh. Mode/theme restano persistiti (UX).
        // Migrazione storage: in passato il token era in sessionStorage —
        // qui leggiamo localStorage (nuovo default), il vecchio dato in
        // sessionStorage viene ignorato. Non c'è rollback necessario:
        // l'utente si riloggia.
        partialize: (s) => ({ mode: s.mode, theme: s.theme }),
      }
    ),
    { name: 'AlembicStore' }
  )
)
