export const OPERATING_MODES = [
  'backtest',
  'paper',
  'semi_auto',
  'full_auto',
  'halted',
  'dry_run',
] as const

export type Mode = typeof OPERATING_MODES[number]
