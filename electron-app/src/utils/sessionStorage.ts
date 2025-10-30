const STORAGE_KEY = 'gmail-labeler-session'

export interface StoredSession {
  userId: string
  email: string
}

export function loadSession(): StoredSession | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredSession>
    if (typeof parsed.userId === 'string' && typeof parsed.email === 'string') {
      return { userId: parsed.userId, email: parsed.email }
    }
  } catch (error) {
    console.warn('[sessionStorage] failed to parse session', error)
  }

  return null
}

export function saveSession(session: StoredSession) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearSession() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(STORAGE_KEY)
}
