import { useEffect, useId, useRef } from 'react'

interface AccessibleModalProps {
  title: string
  children: React.ReactNode
  onClose: () => void
  width?: number
  tone?: 'default' | 'danger' | 'warning'
  closeOnBackdrop?: boolean
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

export function AccessibleModal({ title, children, onClose, width = 460, tone = 'default', closeOnBackdrop = true }: AccessibleModalProps) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  const titleColor = tone === 'danger' ? '#ef4444' : tone === 'warning' ? '#f59e0b' : 'var(--text)'

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    panelRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previousFocus.current?.focus()
    }
  }, [onClose])

  const trapFocus = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab') return
    const nodes = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
      .filter((node) => !node.hasAttribute('disabled'))
    if (nodes.length === 0) {
      event.preventDefault()
      return
    }
    const first = nodes[0]
    const last = nodes[nodes.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      role="presentation"
      onMouseDown={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) onClose()
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.55)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={trapFocus}
        className="card"
        style={{ width, maxWidth: '100%', outline: 'none' }}
      >
        <h3 id={titleId} style={{ margin: '0 0 12px', color: titleColor }}>{title}</h3>
        {children}
      </div>
    </div>
  )
}
