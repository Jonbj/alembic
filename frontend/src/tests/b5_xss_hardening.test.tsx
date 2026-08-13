/**
 * B5 — Frontend XSS / CSP / token storage hardening (issue #41).
 *
 * Questi test descrivono il comportamento atteso, NON l'implementazione.
 * Ogni test è rosso prima del fix e verde dopo. TDD RED→GREEN.
 *
 * Perimetro della issue B5 (Technical Review 2026-07-02):
 *   1. DOMPurify: helper che sanifichi testo non trusted (news, LLM reasoning,
 *      labeling) prima del rendering. Utile anche se oggi non usiamo
 *      dangerouslySetInnerHTML: difende da future regressioni.
 *   2. CSP: meta Content-Security-Policy in index.html con default-src 'self'
 *      e niente unsafe-inline/unsafe-eval.
 *   3. Token storage: rimuovere il JWT da sessionStorage (accessibile a
 *      qualsiasi script in caso di XSS). Lo store resta in-memory only per
 *      il token; mode/theme continuano a persistere.
 *
 * Cosa NON è in scope qui (segnalato nella PR, decisione operatore):
 *   - httpOnly cookie (richiede cambio BE = fuori perimetro freeze-ok solo FE).
 *   - Correzione degli 11 lint errors pre-esistenti (#41 = XSS/CSP/token,
 *     i lint errors sono una sotto-issue diversa in #21).
 */
import { describe, test, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ── 1. Sanitize helper ─────────────────────────────────────────────────────

describe('B5 — sanitizeText / sanitizeUrl', () => {
  test('sanitizeText rimuove <script> anche da testo con entità HTML', async () => {
    const { sanitizeText } = await import('@/utils/sanitize')
    // L'attaccante inietta un tag script come stringa, non come HTML.
    // Se in futuro il testo verrà passato a dangerouslySetInnerHTML o a
    // una libreria markdown, DOMPurify deve neutralizzarlo.
    const out = sanitizeText('<script>alert(1)</script>AAPL +5%')
    expect(out).not.toMatch(/<script/i)
    expect(out).not.toMatch(/alert\(1\)/)
    // Il testo visibile deve restare leggibile.
    expect(out).toContain('AAPL +5%')
  })

  test('sanitizeText rimuove handler di evento e attributi pericolosi', async () => {
    const { sanitizeText } = await import('@/utils/sanitize')
    const out = sanitizeText('<img src=x onerror="alert(1)"><a href="javascript:alert(2)">x</a>')
    expect(out).not.toMatch(/onerror=/i)
    expect(out).not.toMatch(/javascript:/i)
  })

  test('sanitizeUrl accetta solo http(s); rifiuta javascript:, data:, vbscript:', async () => {
    const { sanitizeUrl } = await import('@/utils/sanitize')
    expect(sanitizeUrl('https://example.com/x')).toBe('https://example.com/x')
    expect(sanitizeUrl('http://example.com/x')).toBe('http://example.com/x')
    expect(sanitizeUrl('javascript:alert(1)')).toBeUndefined()
    expect(sanitizeUrl('data:text/html,<script>alert(1)</script>')).toBeUndefined()
    expect(sanitizeUrl('vbscript:msgbox(1)')).toBeUndefined()
    // URL malformati / vuoti
    expect(sanitizeUrl('')).toBeUndefined()
    expect(sanitizeUrl('not a url')).toBeUndefined()
  })

  test('sanitizeUrl ignora whitespace e case variation di javascript:', async () => {
    const { sanitizeUrl } = await import('@/utils/sanitize')
    expect(sanitizeUrl('  JaVaScRiPt:alert(1)')).toBeUndefined()
    expect(sanitizeUrl('\tjavascript:alert(1)')).toBeUndefined()
  })
})

// ── 2. CSP in index.html ───────────────────────────────────────────────────

describe('B5 — Content Security Policy in index.html', () => {
  const indexHtml = readFileSync(resolve(__dirname, '../../index.html'), 'utf-8')

  test('index.html contiene un meta tag Content-Security-Policy', () => {
    expect(indexHtml).toMatch(/<meta[^>]+http-equiv=["']Content-Security-Policy["']/i)
  })

  test('CSP ha default-src \'self\' e non permette unsafe-inline', () => {
    const m = indexHtml.match(/<meta[^>]+Content-Security-Policy[^>]+content=(["'])([\s\S]*?)\1/i)
    expect(m, 'CSP meta tag non trovato').toBeTruthy()
    const csp = m![2]
    expect(csp).toMatch(/default-src\s+['"]self['"]/i)
    // unsafe-inline e unsafe-eval non devono comparire in default-src / script-src
    // (sono accettabili solo se limitati a casi specifici, ma la review
    // 2026-07-02 chiede CSP strict, quindi vietati qui)
    expect(csp).not.toMatch(/unsafe-inline/i)
    expect(csp).not.toMatch(/unsafe-eval/i)
  })

  test('CSP consente i Google Fonts (preconnect/css2) usati dal theme script', () => {
    // Il template index.html linka fonts.googleapis.com + fonts.gstatic.com.
    // La CSP deve lasciarli passare, altrimenti il FE si rompe al boot.
    const m = indexHtml.match(/<meta[^>]+Content-Security-Policy[^>]+content=(["'])([\s\S]*?)\1/i)
    expect(m).toBeTruthy()
    const csp = m![2]
    expect(csp).toMatch(/fonts\.googleapis\.com/)
    expect(csp).toMatch(/fonts\.gstatic\.com/)
  })
})

// ── 3. Token non più in sessionStorage ──────────────────────────────────────

describe('B5 — Token non persistito in sessionStorage', () => {
  test('lo store non include "token" nel partialize persistito', async () => {
    const src = readFileSync(resolve(__dirname, '../store/index.ts'), 'utf-8')
    // Il partialize decide cosa va persistito. Se contiene "token", il JWT
    // resta in sessionStorage accessibile a XSS.
    const partializeMatch = src.match(/partialize\s*:\s*\(([^)]+)\)\s*=>\s*\(?\{([^}]+)\}\)?/m)
    expect(partializeMatch, 'partialize non trovato nello store').toBeTruthy()
    const partialized = partializeMatch![2]
    expect(partialized).not.toMatch(/\btoken\b/)
  })

  test('lo store non usa più sessionStorage per la persistenza', async () => {
    const src = readFileSync(resolve(__dirname, '../store/index.ts'), 'utf-8')
    // Se la chiave sessionStorage è ancora il backend, il token in-memory
    // verrebbe comunque scaricato lì al prossimo set.
    expect(src).not.toMatch(/createJSONStorage\(\(\)\s*=>\s*sessionStorage\)/)
  })

  test('isAuthenticated rimane derivato dal token in-memory', () => {
    // Pur senza persistere, lo store deve continuare a derivare
    // isAuthenticated dal token presente. Verifica statica.
    const src = readFileSync(resolve(__dirname, '../store/index.ts'), 'utf-8')
    expect(src).toMatch(/isAuthenticated:\s*!!token/)
  })

  test('le pagine "untrusted" importano l\'helper sanitize', () => {
    // B5: le 4 pagine flaggate dalla Technical Review (News/LLM/Signals/Labeling)
    // DEVONO passare testo/URL esterni attraverso sanitize. Verifica statica:
    // se qualcuno rimuove l'helper (o renderizza direttamente f.reasoning /
    // item.title / item.url), il test rosso segnala la regressione.
    for (const page of ['News.tsx', 'LLM.tsx', 'Signals.tsx', 'Labeling.tsx']) {
      const src = readFileSync(resolve(__dirname, `../pages/${page}`), 'utf-8')
      expect(src, `${page} non importa più @/utils/sanitize`).toMatch(
        /from\s+['"]@\/utils\/sanitize['"]/
      )
      // Deve usare almeno uno dei due helper. News usa sanitizeUrl per il
      // link esterno, le altre usano sanitizeText per il contenuto.
      expect(
        src,
        `${page} non chiama sanitizeText() né sanitizeUrl()`
      ).toMatch(/sanitize(Text|Url)\(/)
    }
  })
})
