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
}
