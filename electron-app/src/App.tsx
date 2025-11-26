import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

import { clearSession, loadSession, saveSession, type StoredSession } from './utils/sessionStorage'
import type {
  EmailItem,
  OAuthCompletionPayload,
  OAuthStatusResponse,
} from './shared/ipc'
import { PatternViewer } from './components/PatternViewer'
import { AutoFetchSettings } from './components/AutoFetchSettings'

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
  const [emailStats, setEmailStats] = useState<{
    total: number
    important: number
    notImportant: number
    uncategorized: number
    autoLabeled: number
    manualLabeled: number
  } | null>(null)
  const [isFetchingEmails, setIsFetchingEmails] = useState(false)
  const [emailsError, setEmailsError] = useState<string>('')
  const [agentStatuses, setAgentStatuses] = useState<Record<string, string>>({})
  const [labelStatuses, setLabelStatuses] = useState<Record<string, string>>({})

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

      // DEBUG: Log raw response
      console.log('=== EMAIL FETCH DEBUG ===')
      console.log('Total emails fetched:', result.items.length)
      console.log('Stats:', result.stats)
      console.log('First email (raw):', result.items[0])
      if (result.items[0]) {
        console.log('First email label field:', result.items[0].label)
        console.log('First email labelSource field:', result.items[0].labelSource)
        console.log('First email labelConfidence field:', result.items[0].labelConfidence)
      }

      setEmails(result.items)
      setEmailStats(result.stats || null)

      if (result.items.length === 0) {
        setStatusMessage('No recent emails detected. Try again after new mail arrives.')
      } else {
        const stats = result.stats
        const autoCount = stats?.autoLabeled || 0
        setStatusMessage(
          `Fetched ${result.items.length} email(s). ` +
          `${autoCount > 0 ? `${autoCount} auto-labeled! ` : ''}` +
          `(${stats?.important || 0} Important, ${stats?.notImportant || 0} Not Important, ${stats?.uncategorized || 0} Uncategorized)`
        )
      }
    } catch (error) {
      console.error('Failed to fetch emails', error)
      setEmailsError('Unable to fetch emails from the backend. Verify the service is running.')
    } finally {
      setIsFetchingEmails(false)
    }
  }, [api, session])

  // Auto-fetch trigger listener
  useEffect(() => {
    const handleAutoFetchTrigger = () => {
      console.log('Auto-fetch triggered, fetching emails...')
      if (session && isConnected) {
        handleFetchEmails().catch((error) => {
          console.error('Auto-fetch failed:', error)
        })
      }
    }

    window.addEventListener('auto-fetch-trigger', handleAutoFetchTrigger)

    return () => {
      window.removeEventListener('auto-fetch-trigger', handleAutoFetchTrigger)
    }
  }, [session, isConnected, handleFetchEmails])

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

  const handleApplyLabel = useCallback(
    async (email: EmailItem, labelName: string) => {
      if (!session) return

      setLabelStatuses((current) => ({ ...current, [email.id]: `Applying ${labelName}...` }))

      try {
        await api.labels.apply({
          userId: session.userId,
          gmailMessageId: email.gmailMessageId,
          labelName,
        })

        setLabelStatuses((current) => ({
          ...current,
          [email.id]: `Labeled as ${labelName}`,
        }))

        // Refresh email list to show updated labels
        setTimeout(() => {
          setLabelStatuses((current) => {
            const updated = { ...current }
            delete updated[email.id]
            return updated
          })
          void handleFetchEmails()
        }, 1000)
      } catch (error) {
        console.error('Failed to apply label', error)
        setLabelStatuses((current) => ({ ...current, [email.id]: 'Label application failed' }))
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

      {isConnected && <AutoFetchSettings />}

      {emails.length > 0 && (() => {
        // Helper to get email label
        const getEffectiveLabel = (email: EmailItem): string | null => {
          return email.label ?? null
        }

        const importantEmails = emails.filter(
          (email) => getEffectiveLabel(email) === 'Important'
        )
        const notImportantEmails = emails.filter(
          (email) => getEffectiveLabel(email) === 'Not Important'
        )
        const uncategorizedEmails = emails.filter((email) => !getEffectiveLabel(email))

        // DEBUG: Log filtering results
        console.log('=== FILTERING DEBUG ===')
        console.log('Total emails:', emails.length)
        console.log('Important emails:', importantEmails.length, importantEmails.map(e => ({
          subject: e.subject,
          label: e.label,
        })))
        console.log('Not Important emails:', notImportantEmails.length, notImportantEmails.map(e => ({
          subject: e.subject,
          label: e.label,
        })))
        console.log('Uncategorized emails:', uncategorizedEmails.length)

        // Helper function to render label badge with confidence
        const renderLabelBadge = (email: EmailItem) => {
          const label = getEffectiveLabel(email)
          if (!label) return null

          const isAutoLabeled = email.labelSource === 'auto'
          const confidence = email.labelConfidence

          return (
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '4px 12px',
              borderRadius: '16px',
              backgroundColor: isAutoLabeled ? '#e3f2fd' : '#e8f5e9',
              fontSize: '0.85em',
              fontWeight: 500,
            }}>
              <span>{label}</span>
              {isAutoLabeled && confidence && (
                <span style={{
                  padding: '2px 6px',
                  borderRadius: '8px',
                  backgroundColor: '#2196f3',
                  color: 'white',
                  fontSize: '0.9em',
                }}>
                  {Math.round(confidence * 100)}%
                </span>
              )}
              {isAutoLabeled && (
                <span style={{
                  padding: '2px 6px',
                  borderRadius: '8px',
                  backgroundColor: '#ff9800',
                  color: 'white',
                  fontSize: '0.85em',
                  fontWeight: 'bold',
                }}>
                  AUTO
                </span>
              )}
              {email.labelSource === 'manual' && (
                <span style={{
                  padding: '2px 6px',
                  borderRadius: '8px',
                  backgroundColor: '#4caf50',
                  color: 'white',
                  fontSize: '0.85em',
                }}>
                  ✓
                </span>
              )}
            </div>
          )
        }

        return (
          <>
            {importantEmails.length > 0 && (
              <section className='card'>
                <h2>⭐ Important ({importantEmails.length})</h2>
                <p className='hint'>
                  {emailStats ? `${emailStats.important} Important emails` : 'Emails marked as important'}
                </p>
                <ul className='email-list'>
                  {importantEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '12px', marginBottom: '8px' }}>
                        <h3 style={{ margin: 0, flex: 1 }}>{email.subject || '(no subject)'}</h3>
                        {renderLabelBadge(email)}
                      </div>
                      <p className='email-meta'>
                        {email.senderEmail && <span>From: {email.senderEmail} • </span>}
                        Received {new Date(email.receivedAt).toLocaleString()}
                      </p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleApplyLabel(email, 'Not Important')} className='secondary'>
                          Re-mark as Not Important
                        </button>
                        <button type='button' onClick={() => handleRunAgent(email)} className='secondary'>
                          Re-analyze
                        </button>
                      </div>
                      {labelStatuses[email.id] && (
                        <p className='email-status'>{labelStatuses[email.id]}</p>
                      )}
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
                <h2>🗑️ Not Important ({notImportantEmails.length})</h2>
                <p className='hint'>
                  {emailStats ? `${emailStats.notImportant} Not Important emails` : 'Emails marked as not important'}
                </p>
                <ul className='email-list'>
                  {notImportantEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '12px', marginBottom: '8px' }}>
                        <h3 style={{ margin: 0, flex: 1 }}>{email.subject || '(no subject)'}</h3>
                        {renderLabelBadge(email)}
                      </div>
                      <p className='email-meta'>
                        {email.senderEmail && <span>From: {email.senderEmail} • </span>}
                        Received {new Date(email.receivedAt).toLocaleString()}
                      </p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleApplyLabel(email, 'Important')} className='secondary'>
                          Re-mark as Important
                        </button>
                        <button type='button' onClick={() => handleRunAgent(email)} className='secondary'>
                          Re-analyze
                        </button>
                      </div>
                      {labelStatuses[email.id] && (
                        <p className='email-status'>{labelStatuses[email.id]}</p>
                      )}
                      {agentStatuses[email.id] && (
                        <p className='email-status'>{agentStatuses[email.id]}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {uncategorizedEmails.length > 0 && (
              <section className='card'>
                <h2>❓ Uncategorized ({uncategorizedEmails.length})</h2>
                <p className='hint'>
                  {emailStats ? `${emailStats.uncategorized} emails need labeling` : 'Label these emails manually'}
                </p>
                <ul className='email-list'>
                  {uncategorizedEmails.map((email) => (
                    <li key={email.id} className='email-item'>
                      <h3>{email.subject || '(no subject)'}</h3>
                      <p className='email-meta'>
                        {email.senderEmail && <span>From: {email.senderEmail} • </span>}
                        Received {new Date(email.receivedAt).toLocaleString()}
                      </p>
                      {email.snippet && <p className='email-snippet'>{email.snippet}</p>}
                      <div className='email-actions'>
                        <button type='button' onClick={() => handleApplyLabel(email, 'Important')}>
                          Mark as Important
                        </button>
                        <button type='button' onClick={() => handleApplyLabel(email, 'Not Important')}>
                          Mark as Not Important
                        </button>
                        <button type='button' onClick={() => handleRunAgent(email)} className='secondary'>
                          Trigger agent
                        </button>
                      </div>
                      {labelStatuses[email.id] && (
                        <p className='email-status'>{labelStatuses[email.id]}</p>
                      )}
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

      {isConnected && session && (
        <section className='card'>
          <PatternViewer userId={session.userId} />
        </section>
      )}

      <footer className='footer'>
        <p>
          Backend base URL: <code>{import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}</code>
        </p>
      </footer>
    </div>
  )
}

export default App
