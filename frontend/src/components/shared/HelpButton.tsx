import { useState, useEffect, useRef } from 'react'

export interface HelpSection {
  heading: string
  content: string
}

interface HelpButtonProps {
  title: string
  sections: HelpSection[]
}

function renderContent(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return part.split('\n').map((line, j, arr) => (
      <span key={`${i}-${j}`}>
        {line}
        {j < arr.length - 1 && <br />}
      </span>
    ))
  })
}

export function HelpButton({ title, sections }: HelpButtonProps) {
  const [open, setOpen] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const titleId = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-help-title`

  useEffect(() => {
    if (!open) return
    drawerRef.current?.focus()
    function handleClick(e: MouseEvent) {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKeyDown)
      buttonRef.current?.focus()
    }
  }, [open])

  return (
    <>
      <button
        ref={buttonRef}
        onClick={() => setOpen(true)}
        title="Guida e documentazione"
        aria-label={`Apri guida: ${title}`}
        aria-expanded={open}
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: '#3b82f6',
          color: 'white',
          border: 'none',
          cursor: 'pointer',
          fontSize: 14,
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          lineHeight: 1,
          flexShrink: 0,
          zIndex: 10,
        }}
      >
        ?
      </button>

      {open && (
        <div role="presentation" style={{
          position: 'fixed',
          inset: 0,
          zIndex: 1000,
          pointerEvents: 'none',
        }}>
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: 400,
              height: '100%',
              background: '#1e293b',
              borderLeft: '1px solid #334155',
              display: 'flex',
              flexDirection: 'column',
              pointerEvents: 'all',
              animation: 'slideInRight 0.2s ease-out',
            }}
          >
            <style>{`
              @keyframes slideInRight {
                from { transform: translateX(100%); }
                to { transform: translateX(0); }
              }
            `}</style>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '16px 20px',
              borderBottom: '1px solid #334155',
              flexShrink: 0,
            }}>
              <div id={titleId} style={{ color: 'white', fontWeight: 700, fontSize: 15 }}>{title}</div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Chiudi guida"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  fontSize: 18,
                  lineHeight: 1,
                  padding: 4,
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ overflowY: 'auto', padding: '20px', flex: 1 }}>
              {sections.map((sec, i) => (
                <div key={i} style={{ marginBottom: 24 }}>
                  <div style={{
                    color: '#60a5fa',
                    fontWeight: 600,
                    fontSize: 13,
                    marginBottom: 8,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}>
                    {sec.heading}
                  </div>
                  <div style={{
                    color: '#cbd5e1',
                    fontSize: 13,
                    lineHeight: 1.7,
                  }}>
                    {renderContent(sec.content)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
