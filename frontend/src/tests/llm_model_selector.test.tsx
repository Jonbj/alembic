import { describe, test, expect } from 'vitest'
import { activeModelLabel } from '@/utils/llm'
import type { LLMModelInfo } from '@/store'

const MODELS: LLMModelInfo[] = [
  { key: 'glm52', model_id: 'glm-5.2:cloud', label: 'GLM-5.2', active: true, economy_default: true },
  { key: 'gptoss', model_id: 'gpt-oss:20b-cloud', label: 'GPT-OSS 20B', active: true, economy_default: false },
  { key: 'kimi', model_id: 'kimi-k2.6:cloud', label: 'Kimi K2.6', active: false, economy_default: false },
]

describe('LLM model selector label helper', () => {
  test('shows joined short labels for the active pair', () => {
    expect(activeModelLabel(MODELS)).toBe('GLM-5.2 + GPT-OSS')
  })

  test('shows single model label when only one is active', () => {
    expect(activeModelLabel([{ ...MODELS[0], active: true }, { ...MODELS[1], active: false }])).toBe('GLM-5.2')
  })

  test('shows "No models" when nothing is active', () => {
    expect(activeModelLabel(MODELS.map(m => ({ ...m, active: false })))).toBe('No models')
  })
})
