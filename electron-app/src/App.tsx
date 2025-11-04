import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

import { clearSession, loadSession, saveSession, type StoredSession } from './utils/sessionStorage'
import type {
  EmailItem,
  OAuthCompletionPayload,
  OAuthStatusResponse,
} from './shared/ipc'

import './App.css'

type ConnectionState = 'disconnected' | 'connecting' | 'awaiting' | 'connected' | 'error'

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function App() {
  const [session, setSession] = useState<StoredSession | null>(() => loadSession())
  const [emailInput, setEmailInput] = useState(session?.email ?? '')
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [expiresAt, setExpiresAt] = useState<string | undefined>(undefined)
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [emails, setEmails] = useState<EmailItem[]>([])
  const [isFetchingEmails, setIsFetchingEmails] = useState(false)
  const [emailsError, setEmailsError] = useState<string>('')
  const [agentStatuses, setAgentStatuses] = useState<Record<string, string>>({})

  const isConnected = connectionState === 'connected'

  const api = useMemo(() => window.electronAPI, [])

  useEffect(() => {
    const unsubscribe = api.oauth.onComplete((payload: OAuthCompletionPayload) => {
      if (payload.connected) {
        setConnectionState('connected')
        setExpiresAt(payload.expiresAt)
        setStatusMessage('Gmail connection established. You can return to the desktop app.')
        setErrorMessage('')
      } else {
        setConnectionState('error')
        setErrorMessage(payload.error ?? 'Failed to complete Gmail OAuth flow.')
      }
    })

    return () => unsubscribe()
  }, [api])

  useEffect(() => {
    if (!session) return

    let cancelled = false

    api.oauth
      .status(session.userId)
      .then((result: OAuthStatusResponse) => {
        if (cancelled) return
        if (result.connected) {
          setConnectionState('connected')
          setExpiresAt(result.expiresAt)
          setStatusMessage('Connected to Gmail.')
        } else {
          setConnectionState('disconnected')
        }
      })
      .catch((error: unknown) => {
        console.warn('Failed to resolve OAuth status', error)
        if (!cancelled) {
          setConnectionState('disconnected')
        }
      })

    return () => {
      cancelled = true
    }
  }, [api, session])

  const startOAuthFlow = useCallback(
    async (targetSession: StoredSession) => {
      try {
        setConnectionState('connecting')
        setErrorMessage('')
        setStatusMessage('')
        const response = await api.oauth.start({
          userId: targetSession.userId,
          email: targetSession.email,
        })
        setConnectionState('awaiting')
        setStatusMessage(
          'Check your browser to grant access. Once approved, you will be redirected back here automatically.',
        )
        setExpiresAt(undefined)
        console.info('OAuth flow started. Callback URL:', response.callbackUrl)
      } catch (error) {
        console.error('Failed to start OAuth', error)
        setConnectionState('error')
        setErrorMessage('Unable to launch Gmail authorization. Please try again.')
      }
    },
    [api],
  )

  const handleConnect = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      setErrorMessage('')

      const trimmedEmail = emailInput.trim().toLowerCase()
      if (!EMAIL_REGEX.test(trimmedEmail)) {
        setErrorMessage('Enter a valid email address.')
        return
      }

      let nextSession = session
      if (!nextSession || nextSession.email !== trimmedEmail) {
        nextSession = {
          userId: session?.userId ?? crypto.randomUUID(),
          email: trimmedEmail,
        }
        setSession(nextSession)
        saveSession(nextSession)
      }

      await startOAuthFlow(nextSession)
    },
    [emailInput, session, startOAuthFlow],
  )

  const handleReset = useCallback(() => {
    clearSession()
    setSession(null)
    setEmailInput('')
    setConnectionState('disconnected')
    setStatusMessage('')
    setErrorMessage('')
    setExpiresAt(undefined)
    setEmails([])
  }, [])

  const handleFetchEmails = useCallback(async () => {
    if (!session) return
    setIsFetchingEmails(true)
    setEmailsError('')

    try {
      const result = await api.emails.fetch({ userId: session.userId, maxResults: 10 })
      setEmails(result.items)
      if (result.items.length === 0) {
        setStatusMessage('No recent emails detected. Try again after new mail arrives.')
      } else {
        setStatusMessage(`Fetched ${result.items.length} email(s).`)
      }
    } catch (error) {
      console.error('Failed to fetch emails', error)
      setEmailsError('Unable to fetch emails from the backend. Verify the service is running.')
    } finally {
      setIsFetchingEmails(false)
    }
  }, [api, session])

  const handleReconnect = useCallback(() => {
    if (!session) return
    void startOAuthFlow(session)
  }, [session, startOAuthFlow])

  const handleRunAgent = useCallback(
    async (email: EmailItem) => {
      if (!session) return

      setAgentStatuses((current) => ({ ...current, [email.id]: 'Submitting run…' }))

      try {
        const run = await api.runs.trigger({
          userId: session.userId,
          emailId: email.id,
          gmailMessageId: email.gmailMessageId,
        })

        setAgentStatuses((current) => ({ ...current, [email.id]: `Run queued (${run.status})` }))

        const status = await api.runs.status(run.runId)
        setAgentStatuses((current) => ({
          ...current,
          [email.id]: status.status === 'completed'
            ? 'Run completed'
            : `Run status: ${status.status}`,
        }))

        // Refresh email list to show updated agent suggestions
        if (status.status === 'completed') {
          await handleFetchEmails()
        }
      } catch (error) {
        console.error('Failed to trigger agent run', error)
        setAgentStatuses((current) => ({ ...current, [email.id]: 'Agent run failed' }))
      }
    },
    [api, session, handleFetchEmails],
  )

  return (
    <div className='App'>
      <header>
        <h1>Gmail Labeler Desktop</h1>
        <p className='subtitle'>Connect your Gmail account so the agent runtime can label messages automatically.</p>
      </header>

      {!isConnected && (
        <section className='card'>
          <h2>Onboarding</h2>
          <form onSubmit={handleConnect} className='form'>
            <label className='form-label' htmlFor='email'>
              Gmail address
            </label>
            <input
              id='email'
              type='email'
              value={emailInput}
              onChange={(event) => setEmailInput(event.target.value)}
              placeholder='name@example.com'
              className='input'
              required
            />
            <button type='submit' disabled={connectionState === 'connecting' || connectionState === 'awaiting'}>
              {connectionState === 'connecting' ? 'Launching OAuth…' : connectionState === 'awaiting' ? 'Waiting for approval…' : 'Connect Gmail'}
            </button>
            {session && (
              <p className='hint'>Session ID: <code>{session.userId}</code></p>
            )}
          </form>
          {statusMessage && <p className='status status--info'>{statusMessage}</p>}
          {errorMessage && <p className='status status--error'>{errorMessage}</p>}
        </section>
      )}

      {isConnected && (
        <section className='card'>
          <h2>Connection</h2>
          <p className='status status--success'>Connected to Gmail as {session?.email}</p>
          {expiresAt && <p className='hint'>Token expires: {new Date(expiresAt).toLocaleString()}</p>}
          <div className='actions'>
            <button type='button' onClick={handleFetchEmails} disabled={isFetchingEmails}>
              {isFetchingEmails ? 'Fetching…' : 'Fetch latest emails'}
            </button>
            <button type='button' onClick={handleReconnect}>
              Re-run OAuth
            </button>
            <button type='button' className='secondary' onClick={handleReset}>
              Reset onboarding
            </button>
          </div>
          {statusMessage && <p className='status status--info'>{statusMessage}</p>}
          {emailsError && <p className='status status--error'>{emailsError}</p>}
        </section>
      )}

      {emails.length > 0 && (() => {
        const importantEmails = emails.filter(
          (email) => email.agentSuggestion?.toLowerCase() === 'important'
        )
        const notImportantEmails = emails.filter(
          (email) => email.agentSuggestion?.toLowerCase() === 'not important'
        )
        const unanalyzedEmails = emails.filter((email) => !email.agentSuggestion)

        return (
          <>
            {importantEmails.length > 0 && (
              <section className='card'>
                <h2>🔴 Important Emails ({importantEmails.length})</h2>
                <p className='hint'>AI classified these as important</p>
                <ul className='email-list'>
                  {importantEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <h3>{email.subject || '(no subject)'}</h3>
                      <p className='email-meta'>Received {new Date(email.receivedAt).toLocaleString()}</p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <p className='email-suggestion'>AI Suggestion: {email.agentSuggestion}</p>
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleRunAgent(email)}>
                          Re-analyze
                        </button>
                      </div>
                      {agentStatuses[email.id] && (
                        <p className='email-status'>{agentStatuses[email.id]}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {notImportantEmails.length > 0 && (
              <section className='card'>
                <h2>⚪ Not Important ({notImportantEmails.length})</h2>
                <p className='hint'>AI classified these as not important</p>
                <ul className='email-list'>
                  {notImportantEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <h3>{email.subject || '(no subject)'}</h3>
                      <p className='email-meta'>Received {new Date(email.receivedAt).toLocaleString()}</p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <p className='email-suggestion'>AI Suggestion: {email.agentSuggestion}</p>
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleRunAgent(email)}>
                          Re-analyze
                        </button>
                      </div>
                      {agentStatuses[email.id] && (
                        <p className='email-status'>{agentStatuses[email.id]}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {unanalyzedEmails.length > 0 && (
              <section className='card'>
                <h2>📧 Unanalyzed Emails ({unanalyzedEmails.length})</h2>
                <p className='hint'>Click "Trigger agent" to get AI classification</p>
                <ul className='email-list'>
                  {unanalyzedEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <h3>{email.subject || '(no subject)'}</h3>
                      <p className='email-meta'>Received {new Date(email.receivedAt).toLocaleString()}</p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleRunAgent(email)}>
                          Trigger agent
                        </button>
                      </div>
                      {agentStatuses[email.id] && (
                        <p className='email-status'>{agentStatuses[email.id]}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )
      })()}

      <footer className='footer'>
        <p>
          Backend base URL: <code>{import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}</code>
        </p>
      </footer>
    </div>
  )
}

export default App
