import { create } from 'zustand'
import { persist, devtools, createJSONStorage } from 'zustand/middleware'

type Mode = 'backtest' | 'paper' | 'semi_auto' | 'full_auto' | 'halted'
type Theme = 'dark' | 'light'

interface AppState {
  mode: Mode
  theme: Theme
  killswitchActive: boolean
  token: string
  isAuthenticated: boolean
  llmModels: string  // "all" = full ensemble, "glm" = savings mode
  setMode: (mode: Mode) => void
  setTheme: (theme: Theme) => void
  setKillswitch: (active: boolean) => void
  setToken: (token: string) => void
  logout: () => void
  setLlmModels: (models: string) => void
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
        setMode: (mode) => set({ mode }),
        setTheme: (theme) => set({ theme }),
        setKillswitch: (killswitchActive) => set({ killswitchActive }),
        setToken: (token) => set({ token, isAuthenticated: !!token }),
        logout: () => set({ token: '', isAuthenticated: false }),
        setLlmModels: (llmModels) => set({ llmModels }),
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
