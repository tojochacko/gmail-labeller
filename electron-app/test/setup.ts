import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

const oauthStartMock = vi.fn(() => Promise.resolve({
  authorizationUrl: 'https://example.com',
  state: 'test-state',
  callbackUrl: 'http://127.0.0.1:3005/oauth/callback',
}))

const oauthStatusMock = vi.fn(() => Promise.resolve({ connected: false }))
let oauthCompleteHandler: ((payload: any) => void) | null = null

const emailsFetchMock = vi.fn(() =>
  Promise.resolve({
    items: [
      {
        id: '1',
        gmail_message_id: 'gm-1',
        thread_id: 'th-1',
        subject: 'Test email',
        snippet: 'Hello world',
        received_at: new Date().toISOString(),
        processed_at: null,
        agent_suggestion: null,
      },
    ],
  }),
)

const labelsApplyMock = vi.fn(() => Promise.resolve({ success: true, applied_label: 'AUTO' }))
const runsTriggerMock = vi.fn(() => Promise.resolve({ run_id: 'run-1', status: 'queued' }))
const runsStatusMock = vi.fn(() =>
  Promise.resolve({
    run_id: 'run-1',
    status: 'completed',
    result_payload: { summary: 'done' },
    updated_at: new Date().toISOString(),
  }),
)

Object.assign(window, {
  electronAPI: {
    oauth: {
      start: oauthStartMock,
      status: oauthStatusMock,
      onComplete: (handler: (payload: unknown) => void) => {
        oauthCompleteHandler = handler
        return () => {
          oauthCompleteHandler = null
        }
      },
    },
    emails: {
      fetch: emailsFetchMock,
    },
    labels: {
      apply: labelsApplyMock,
    },
    runs: {
      trigger: runsTriggerMock,
      status: runsStatusMock,
    },
  },
})

export function emitOAuthCompletion(payload: any) {
  oauthCompleteHandler?.(payload)
}

export const oauthMocks = {
  oauthStartMock,
  oauthStatusMock,
  emailsFetchMock,
  labelsApplyMock,
  runsTriggerMock,
  runsStatusMock,
} satisfies Record<string, ReturnType<typeof vi.fn>>
