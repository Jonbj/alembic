/**
 * Trace drawer — strategy origin for non-news orders.
 *
 * An S1 momentum order has no news/signal behind it by design: the drawer must
 * say so ("origin: S1 momentum") instead of the misleading generic
 * "not traced / no linked downstream record".
 */
import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { MemoryRouter } from 'react-router-dom'
import { SignalTraceLinks } from '@/components/shared/SignalTraceLinks'

function renderTrace(availability: Record<string, unknown>) {
  return render(
    <MemoryRouter>
      <SignalTraceLinks symbol="AAPL" availability={availability} />
    </MemoryRouter>,
  )
}

describe('SignalTraceLinks strategy origin', () => {
  test('S1 origin replaces "not traced" with the momentum origin on news and signal steps', async () => {
    renderTrace({
      orderId: 'ord-1',
      orderCount: 1,
      signalCount: 0,
      decisionCount: 1,
      decisionId: 5,
      originStrategy: 'S1',
    })

    await userEvent.click(screen.getByRole('button', { name: 'Trace' }))

    // News + Signal steps both carry the origin badge instead of "not traced".
    expect(screen.getAllByText('S1 · momentum').length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByText('not traced')).not.toBeInTheDocument()
    expect(screen.queryByText(/No linked downstream record/)).not.toBeInTheDocument()
    expect(screen.getAllByText(/no news is expected/i).length).toBeGreaterThanOrEqual(1)
  })

  test('without an origin, untraced steps keep the generic message', async () => {
    renderTrace({
      orderId: 'ord-2',
      orderCount: 1,
      signalCount: 0,
      decisionCount: 0,
    })

    await userEvent.click(screen.getByRole('button', { name: 'Trace' }))

    expect(screen.getAllByText('not traced').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText(/No linked downstream record/).length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByText('S1 · momentum')).not.toBeInTheDocument()
  })
})

describe('SignalTraceLinks news deep link', () => {
  test('Open News points at the exact article, not just the ticker feed', async () => {
    renderTrace({
      newsId: 9279,
      signalId: 9279,
      decisionId: 16131,
      orderId: '711c0240-4d6c-4a61-9edf-688723e48265',
      orderCount: 1,
      signalCount: 1,
      decisionCount: 1,
    })

    await userEvent.click(screen.getByRole('button', { name: 'Trace' }))

    const openNews = screen.getByRole('link', { name: 'Open News' })
    const href = openNews.getAttribute('href') ?? ''
    expect(href).toContain('news_id=9279')
    expect(href).toContain('ticker=AAPL')
  })
})
