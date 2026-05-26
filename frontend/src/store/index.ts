import { create } from 'zustand'
import { persist, devtools, createJSONStorage } from 'zustand/middleware'

type Mode = 'backtest' | 'paper' | 'semi_auto' | 'full_auto' | 'halted'
type Theme = 'dark' | 'light'

interface AppState {
  mode: Mode
  theme: Theme
  killswitchActive: boolean
  apiKey: string
  llmModels: string  // "all" = full ensemble, "glm" = savings mode
  setMode: (mode: Mode) => void
  setTheme: (theme: Theme) => void
  setKillswitch: (active: boolean) => void
  setApiKey: (key: string) => void
  setLlmModels: (models: string) => void
}

export const useStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'paper',
        theme: 'dark',
        killswitchActive: false,
        apiKey: '',
        llmModels: 'all',
        setMode: (mode) => set({ mode }),
        setTheme: (theme) => set({ theme }),
        setKillswitch: (killswitchActive) => set({ killswitchActive }),
        setApiKey: (apiKey) => set({ apiKey }),
        setLlmModels: (llmModels) => set({ llmModels }),
      }),
      {
        name: 'alembic-store',
        storage: createJSONStorage(() => sessionStorage),
        partialize: (s) => ({ apiKey: s.apiKey, mode: s.mode, theme: s.theme }),
      }
    ),
    { name: 'AlembicStore' }
  )
)
