import type { LLMModelInfo } from '@/store'

export function activeModelLabel(models: LLMModelInfo[]): string {
  const active = models.filter((model) => model.active)
  if (active.length === 0) return 'No models'
  if (active.length === 1) return active[0].label
  return active.map((model) => model.label.split(' ')[0]).join(' + ')
}
