import http, { type IncomingMessage, type ServerResponse } from 'node:http'
import { URL } from 'node:url'

import type { BrowserWindow, WebContents } from 'electron'

import { apiClient } from './api-client'

interface OAuthSession {
  state: string
  userId: string
  webContentsId: number
}

interface OAuthCallbackResult {
  connected: boolean
  expiresAt?: string
  error?: string
}

type CompletionHandler = (session: OAuthSession, result: OAuthCallbackResult) => void

const sessions = new Map<string, OAuthSession>()

let server: http.Server | null = null
let listeningPort: number | null = null
let completionHandler: CompletionHandler | null = null

const SUCCESS_HTML = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Gmail Connected</title>
    <style>
      body { font-family: system-ui, sans-serif; background: #f5f5f5; margin: 0; padding: 3rem; text-align: center; }
      .card { background: #fff; border-radius: 12px; padding: 2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }
      h1 { margin-top: 0; color: #2563eb; }
      p { color: #475569; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Connection Complete</h1>
      <p>You can now return to the Gmail Labeler app.</p>
    </div>
  </body>
</html>`

const ERROR_HTML = (message: string) => `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Connection Error</title>
    <style>
      body { font-family: system-ui, sans-serif; background: #fef2f2; margin: 0; padding: 3rem; text-align: center; }
      .card { background: #fff; border-radius: 12px; padding: 2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }
      h1 { margin-top: 0; color: #dc2626; }
      p { color: #991b1b; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Connection Failed</h1>
      <p>${message}</p>
    </div>
  </body>
</html>`

function sendHtml(res: ServerResponse, statusCode: number, html: string) {
  res.writeHead(statusCode, {
    'Content-Type': 'text/html',
    'Content-Length': Buffer.byteLength(html),
  })
  res.end(html)
}

async function handleCallback(req: IncomingMessage, res: ServerResponse, port: number) {
  const url = new URL(req.url ?? '/', `http://127.0.0.1:${port}`)
  if (url.pathname !== '/oauth/callback') {
    sendHtml(res, 404, ERROR_HTML('Unknown callback path.'))
    return
  }

  const state = url.searchParams.get('state')
  const code = url.searchParams.get('code')

  if (!state || !code) {
    sendHtml(res, 400, ERROR_HTML('Missing OAuth parameters.'))
    return
  }

  const session = sessions.get(state)

  if (!session) {
    sendHtml(res, 400, ERROR_HTML('Session expired. Please restart the connection.'))
    return
  }

  try {
    const result = await apiClient.request<{ connected: boolean; expires_at?: string }>(
      '/api/oauth/callback',
      {
        method: 'POST',
        body: JSON.stringify({
          user_id: session.userId,
          state,
          code,
        }),
      },
    )

    sessions.delete(state)
    sendHtml(res, 200, SUCCESS_HTML)

    completionHandler?.(session, {
      connected: result.connected,
      expiresAt: result.expires_at,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unexpected error'
    sendHtml(res, 500, ERROR_HTML('Failed to complete OAuth handshake.'))
    completionHandler?.(session, {
      connected: false,
      error: message,
    })
  }
}

function ensureServer() {
  if (server) {
    return listeningPort!
  }

  const desiredPort = Number.parseInt(process.env.OAUTH_CALLBACK_PORT ?? '3005', 10)

  server = http.createServer((req, res) => {
    if (!listeningPort) {
      res.statusCode = 500
      res.end('Server not ready')
      return
    }

    if (req.method === 'GET') {
      void handleCallback(req, res, listeningPort)
      return
    }

    sendHtml(res, 405, ERROR_HTML('Method not allowed.'))
  })

  server.on('error', (error) => {
    console.error('[oauth-server] error', error)
  })

  server.listen(desiredPort, '127.0.0.1', () => {
    const address = server?.address()
    if (address && typeof address === 'object') {
      listeningPort = address.port
    } else {
      listeningPort = desiredPort
    }
    console.info(`[oauth-server] listening on http://127.0.0.1:${listeningPort}`)
  })

  return desiredPort
}

export function registerOAuthSession(session: OAuthSession) {
  sessions.set(session.state, session)
}

export function initOAuthServer(handler: CompletionHandler) {
  completionHandler = handler
  return ensureServer()
}

export function stopOAuthServer() {
  if (!server) return
  server.close()
  server = null
  listeningPort = null
  sessions.clear()
  completionHandler = null
}

export function findWebContents(session: OAuthSession, allWindows: BrowserWindow[]): WebContents | null {
  const target = allWindows.find(win => win.webContents.id === session.webContentsId)
  return target?.webContents ?? null
}

export function getCallbackUrl() {
  const port = listeningPort ?? Number.parseInt(process.env.OAUTH_CALLBACK_PORT ?? '3005', 10)
  return `http://127.0.0.1:${port}/oauth/callback`
}
