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
  receivedAt: string
  processedAt?: string | null
  agentSuggestion?: string | null
}

export interface EmailFetchResponse {
  items: EmailItem[]
}

export interface ApplyLabelRequest {
  userId: string
  gmailMessageId: string
  labelName: string
  gmailLabelId?: string | null
}

export interface ApplyLabelResponse {
  success: boolean
  appliedLabel: string
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
