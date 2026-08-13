/**
 * B5 — Frontend XSS / CSP / token storage hardening (issue #41).
 *
 * Helper di sanificazione per testi non trusted (news, LLM reasoning,
 * labeling) e URL. La regola del gioco: il testo esterno deve passare
 * SEMPRE da qui prima di finire in un qualsiasi renderer HTML, presente
 * o futuro. Oggi non usiamo dangerouslySetInnerHTML (React escapa i
 * children di default); questi helper sono la difesa di profondità per
 * future regressioni (es. una libreria markdown che usa innerHTML).
 */
import DOMPurify from 'dompurify'

/**
 * Sanifica testo non trusted per render HTML.
 *
 * - Rimuove `<script>`, `<iframe>`, handler di evento (onclick/onerror/...),
 *   schemi pericolosi (javascript:, data:, vbscript:).
 * - Restituisce HTML, NON testo puro: l'output è sicuro per
 *   dangerouslySetInnerHTML o per librerie markdown.
 * - Se nel testo sono presenti solo caratteri stampabili, vengono preservati.
 */
export function sanitizeText(input: string | null | undefined): string {
  if (input == null) return ''
  // DOMPurify è in modalità browser (Vite/jsdom): lasciamo i default,
  // che sono ALLOWED_TAGS/ATTR ristretti a quelli sicuri. Niente form,
  // niente input, niente script/iframe/object/embed.
  return DOMPurify.sanitize(String(input), {
    USE_PROFILES: { html: true },
  })
}

/**
 * Restituisce l'URL se è http(s) e ben formato; altrimenti undefined.
 * Usato per tutti gli `href` costruiti da input esterno (es. news.url).
 *
 * Casi accettati: http://, https://
 * Casi rifiutati: javascript:, data:, vbscript:, file:, blob:, URL malformati,
 * stringa vuota, spazi bianchi attorno.
 */
export function sanitizeUrl(url: string | null | undefined): string | undefined {
  if (url == null) return undefined
  const trimmed = String(url).trim()
  if (!trimmed) return undefined
  try {
    const parsed = new URL(trimmed)
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return parsed.toString()
    }
    return undefined
  } catch {
    return undefined
  }
}
