import { create } from 'zustand'
import { persist, devtools, createJSONStorage } from 'zustand/middleware'

type Mode = 'backtest' | 'paper' | 'semi_auto' | 'full_auto' | 'halted'

interface AppState {
  mode: Mode
  killswitchActive: boolean
  apiKey: string
  setMode: (mode: Mode) => void
  setKillswitch: (active: boolean) => void
  setApiKey: (key: string) => void
}

export const useStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'paper',
        killswitchActive: false,
        apiKey: '',
        setMode: (mode) => set({ mode }),
        setKillswitch: (killswitchActive) => set({ killswitchActive }),
        setApiKey: (apiKey) => set({ apiKey }),
      }),
      {
        name: 'alembic-store',
        storage: createJSONStorage(() => sessionStorage),
        partialize: (s) => ({ apiKey: s.apiKey, mode: s.mode }),
      }
    ),
    { name: 'AlembicStore' }
  )
)
