import { app, BrowserWindow, shell, ipcMain, type IpcMainInvokeEvent } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import os from 'node:os'
import { config as loadEnv } from 'dotenv'

import type {
  AgentRunRequest,
  ApplyLabelRequest,
  EmailFetchRequest,
  EmailItem,
  OAuthStartRequest,
} from '../../src/shared/ipc'
import { apiClient } from './api-client'
import {
  findWebContents,
  getCallbackUrl,
  initOAuthServer,
  registerOAuthSession,
  stopOAuthServer,
} from './oauth-server'
import { update } from './update'

loadEnv()

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬ dist-electron
// │ ├─┬ main
// │ │ └── index.js    > Electron-Main
// │ └─┬ preload
// │   └── index.mjs   > Preload-Scripts
// ├─┬ dist
// │ └── index.html    > Electron-Renderer
//
process.env.APP_ROOT = path.join(__dirname, '../..')

export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')
export const VITE_DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL
  ? path.join(process.env.APP_ROOT, 'public')
  : RENDERER_DIST

// Disable GPU Acceleration for Windows 7
if (os.release().startsWith('6.1')) app.disableHardwareAcceleration()

// Set application name for Windows 10+ notifications
if (process.platform === 'win32') app.setAppUserModelId(app.getName())

if (!app.requestSingleInstanceLock()) {
  app.quit()
  process.exit(0)
}

let win: BrowserWindow | null = null
const preload = path.join(__dirname, '../preload/index.mjs')
const indexHtml = path.join(RENDERER_DIST, 'index.html')

let oauthServerInitialised = false

function ensureOAuthServer() {
  if (!oauthServerInitialised) {
    initOAuthServer((session, result) => {
      const window = findWebContents(session, BrowserWindow.getAllWindows())
      window?.send('oauth:complete', {
        connected: result.connected,
        expiresAt: result.expiresAt,
        error: result.error,
      })
    })
    oauthServerInitialised = true
  }

  return getCallbackUrl()
}

async function createWindow() {
  win = new BrowserWindow({
    title: 'Main window',
    icon: path.join(process.env.VITE_PUBLIC, 'favicon.ico'),
    webPreferences: {
      preload,
      // Warning: Enable nodeIntegration and disable contextIsolation is not secure in production
      // nodeIntegration: true,

      // Consider using contextBridge.exposeInMainWorld
      // Read more on https://www.electronjs.org/docs/latest/tutorial/context-isolation
      // contextIsolation: false,
    },
  })

  if (VITE_DEV_SERVER_URL) { // #298
    await win.loadURL(VITE_DEV_SERVER_URL)
    // Open devTool if the app is not packaged
    win.webContents.openDevTools()
  } else {
    await win.loadFile(indexHtml)
  }

  // Make all links open with the browser, not with the application
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https:')) shell.openExternal(url)
    return { action: 'deny' }
  })

  // Auto update
  update(win)
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  win = null
  stopOAuthServer()
  oauthServerInitialised = false
  if (process.platform !== 'darwin') app.quit()
})

app.on('second-instance', () => {
  if (win) {
    // Focus on the main window if the user tried to open another
    if (win.isMinimized()) win.restore()
    win.focus()
  }
})

app.on('activate', () => {
  const allWindows = BrowserWindow.getAllWindows()
  if (allWindows.length) {
    allWindows[0].focus()
  } else {
    createWindow()
  }
})

type BackendEmailItem = {
  id: string
  gmail_message_id: string
  thread_id: string
  subject?: string | null
  snippet?: string | null
  received_at?: string | null
  processed_at?: string | null
  agent_suggestion?: string | null
}

type BackendEmailList = {
  items: BackendEmailItem[]
}

function mapEmailResponse(item: BackendEmailItem): EmailItem {
  return {
    id: item.id,
    gmailMessageId: item.gmail_message_id,
    threadId: item.thread_id,
    subject: item.subject ?? '',
    snippet: item.snippet ?? null,
    receivedAt: item.received_at ?? new Date().toISOString(),
    processedAt: item.processed_at ?? null,
    agentSuggestion: item.agent_suggestion ?? null,
  }
}

ipcMain.handle(
  'oauth:start',
  async (event: IpcMainInvokeEvent, payload: OAuthStartRequest) => {
  const callbackUrl = ensureOAuthServer()

  const result = await apiClient.request<{ authorization_url: string; state: string }>(
    '/api/oauth/start',
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: payload.userId,
        email: payload.email,
      }),
    },
  )

  registerOAuthSession({
    state: result.state,
    userId: payload.userId,
    webContentsId: event.sender.id,
  })

  await shell.openExternal(result.authorization_url)

  return {
    authorizationUrl: result.authorization_url,
    state: result.state,
    callbackUrl,
  }
  },
)

ipcMain.handle(
  'oauth:status',
  async (_event: IpcMainInvokeEvent, args: { userId: string }) => {
  try {
    const result = await apiClient.request<{ connected: boolean; expires_at?: string }>(
      `/api/oauth/status/${args.userId}`,
    )
    return {
      connected: result.connected,
      expiresAt: result.expires_at,
    }
  } catch {
    return {
      connected: false,
    }
  }
  },
)

ipcMain.handle(
  'emails:fetch',
  async (_event: IpcMainInvokeEvent, payload: EmailFetchRequest) => {
  const result = await apiClient.request<BackendEmailList>('/api/emails', {
    searchParams: {
      user_id: payload.userId,
      max_results: payload.maxResults ?? 20,
    },
  })

  return {
    items: result.items.map(mapEmailResponse),
  }
  },
)

ipcMain.handle(
  'labels:apply',
  async (_event: IpcMainInvokeEvent, payload: ApplyLabelRequest) => {
  const result = await apiClient.request<{ success: boolean; applied_label: string }>(
    '/api/labels',
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: payload.userId,
        gmail_message_id: payload.gmailMessageId,
        label_name: payload.labelName,
        gmail_label_id: payload.gmailLabelId,
      }),
    },
  )

  return {
    success: result.success,
    appliedLabel: result.applied_label,
  }
  },
)

ipcMain.handle(
  'runs:trigger',
  async (_event: IpcMainInvokeEvent, payload: AgentRunRequest) => {
  const result = await apiClient.request<{ run_id: string; status: string }>(
    '/api/runs',
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: payload.userId,
        email_id: payload.emailId,
        gmail_message_id: payload.gmailMessageId,
        prompt: payload.prompt,
      }),
    },
  )

  return {
    runId: result.run_id,
    status: result.status,
  }
  },
)

ipcMain.handle(
  'runs:status',
  async (_event: IpcMainInvokeEvent, args: { runId: string }) => {
  const result = await apiClient.request<{
    run_id: string
    status: string
    result_payload?: Record<string, unknown>
    updated_at: string
    error_message?: string
  }>(`/api/runs/${args.runId}`)

  return {
    runId: result.run_id,
    status: result.status,
    resultPayload: result.result_payload ?? null,
    updatedAt: result.updated_at,
    errorMessage: result.error_message ?? null,
  }
  },
)
