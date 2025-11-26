export interface OAuthStartRequest {
  userId: string
  email: string
}

export interface OAuthStartResponse {
  authorizationUrl: string
  state: string
  callbackUrl: string
}

export interface OAuthStatusResponse {
  connected: boolean
  expiresAt?: string
}

export interface OAuthCompletionPayload {
  connected: boolean
  expiresAt?: string
  error?: string
}

export interface EmailFetchRequest {
  userId: string
  maxResults?: number
}

export interface EmailItem {
  id: string
  gmailMessageId: string
  threadId: string
  subject: string
  snippet?: string | null
  senderEmail?: string | null
  senderDomain?: string | null
  receivedAt: string
  processedAt?: string | null
  // NEW: Consolidated label fields (post-migration)
  label?: string | null  // "Important", "Not Important", or null for Uncategorized
  labelConfidence?: number | null  // 0.0-1.0 confidence score
  labelSource?: 'auto' | 'manual' | 'agent' | null  // Source of label
  labeledAt?: string | null  // ISO timestamp when labeled
  lastUpdatedBy?: 'auto' | 'user' | 'agent' | null  // Last updater
}

export interface EmailStats {
  total: number
  important: number
  notImportant: number
  uncategorized: number
  autoLabeled: number
  manualLabeled: number
}

export interface EmailFetchResponse {
  items: EmailItem[]
  stats: EmailStats
}

export interface ApplyLabelRequest {
  userId: string
  gmailMessageId: string
  labelName: string
  gmailLabelId?: string | null
}

export interface ApplyLabelResponse {
  success: boolean
  label: string
}

export interface AgentRunRequest {
  userId: string
  emailId: string
  gmailMessageId: string
  prompt?: string | null
}

export interface AgentRunResponse {
  runId: string
  status: string
}

export interface AgentRunStatusResponse {
  runId: string
  status: string
  resultPayload?: Record<string, unknown> | null
  updatedAt: string
  errorMessage?: string | null
}

// Auto-fetch types
export interface AutoFetchSettings {
  enabled: boolean
  intervalMinutes: number
  notificationsEnabled: boolean
  lastFetchTimestamp: string | null
  fetchOnStartup: boolean
}

export interface AutoFetchStatus {
  enabled: boolean
  intervalMinutes: number
  lastFetchTimestamp: string | null
  isRunning: boolean
  retryCount: number
  nextFetchIn: number | null
}

export interface AutoFetchStartResponse {
  success: boolean
  status?: AutoFetchStatus
  error?: string
}

export interface AutoFetchStopResponse {
  success: boolean
  status?: AutoFetchStatus
  error?: string
}

export interface AutoFetchUpdateResponse {
  success: boolean
  status?: AutoFetchStatus
  error?: string
}

export interface AutoFetchFetchNowResponse {
  success: boolean
  result?: {
    success: boolean
    newEmailCount: number
    stats: {
      total: number
      important: number
      notImportant: number
      uncategorized: number
      autoLabeled: number
    }
    error?: string
  }
  error?: string
}

export interface AutoFetchStatusChangedPayload {
  event: string
  data?: any
  status: AutoFetchStatus
}

export interface ElectronAPI {
  oauth: {
    start: (payload: OAuthStartRequest) => Promise<OAuthStartResponse>
    status: (userId: string) => Promise<OAuthStatusResponse>
    onComplete: (handler: (payload: OAuthCompletionPayload) => void) => () => void
  }
  emails: {
    fetch: (payload: EmailFetchRequest) => Promise<EmailFetchResponse>
  }
  labels: {
    apply: (payload: ApplyLabelRequest) => Promise<ApplyLabelResponse>
  }
  runs: {
    trigger: (payload: AgentRunRequest) => Promise<AgentRunResponse>
    status: (runId: string) => Promise<AgentRunStatusResponse>
  }
  autoFetch: {
    start: (settings: Partial<AutoFetchSettings>) => Promise<AutoFetchStartResponse>
    stop: () => Promise<AutoFetchStopResponse>
    getStatus: () => Promise<AutoFetchStatus>
    updateSettings: (settings: Partial<AutoFetchSettings>) => Promise<AutoFetchUpdateResponse>
    fetchNow: () => Promise<AutoFetchFetchNowResponse>
    onStatusChanged: (handler: (payload: AutoFetchStatusChangedPayload) => void) => () => void
  }
}
