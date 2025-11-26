import { ipcRenderer, contextBridge } from 'electron'
import type {
  AgentRunRequest,
  AgentRunResponse,
  AgentRunStatusResponse,
  ApplyLabelRequest,
  ApplyLabelResponse,
  AutoFetchFetchNowResponse,
  AutoFetchSettings,
  AutoFetchStartResponse,
  AutoFetchStatus,
  AutoFetchStatusChangedPayload,
  AutoFetchStopResponse,
  AutoFetchUpdateResponse,
  EmailFetchRequest,
  EmailFetchResponse,
  ElectronAPI,
  OAuthCompletionPayload,
  OAuthStartRequest,
  OAuthStartResponse,
  OAuthStatusResponse,
} from '../../src/shared/ipc'

const electronAPI: ElectronAPI = {
  oauth: {
    start: (payload: OAuthStartRequest) => ipcRenderer.invoke('oauth:start', payload) as Promise<OAuthStartResponse>,
    status: (userId: string) => ipcRenderer.invoke('oauth:status', { userId }) as Promise<OAuthStatusResponse>,
    onComplete: (handler: (payload: OAuthCompletionPayload) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, data: OAuthCompletionPayload) => handler(data)
      ipcRenderer.on('oauth:complete', listener)
      return () => ipcRenderer.removeListener('oauth:complete', listener)
    },
  },
  emails: {
    fetch: (payload: EmailFetchRequest) => ipcRenderer.invoke('emails:fetch', payload) as Promise<EmailFetchResponse>,
  },
  labels: {
    apply: (payload: ApplyLabelRequest) => ipcRenderer.invoke('labels:apply', payload) as Promise<ApplyLabelResponse>,
  },
  runs: {
    trigger: (payload: AgentRunRequest) => ipcRenderer.invoke('runs:trigger', payload) as Promise<AgentRunResponse>,
    status: (runId: string) => ipcRenderer.invoke('runs:status', { runId }) as Promise<AgentRunStatusResponse>,
  },
  autoFetch: {
    start: (settings: Partial<AutoFetchSettings>) =>
      ipcRenderer.invoke('auto-fetch:start', settings) as Promise<AutoFetchStartResponse>,
    stop: () => ipcRenderer.invoke('auto-fetch:stop') as Promise<AutoFetchStopResponse>,
    getStatus: () => ipcRenderer.invoke('auto-fetch:get-status') as Promise<AutoFetchStatus>,
    updateSettings: (settings: Partial<AutoFetchSettings>) =>
      ipcRenderer.invoke('auto-fetch:update-settings', settings) as Promise<AutoFetchUpdateResponse>,
    fetchNow: () => ipcRenderer.invoke('auto-fetch:fetch-now') as Promise<AutoFetchFetchNowResponse>,
    onStatusChanged: (handler: (payload: AutoFetchStatusChangedPayload) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, data: AutoFetchStatusChangedPayload) =>
        handler(data)
      ipcRenderer.on('auto-fetch:status-changed', listener)
      return () => ipcRenderer.removeListener('auto-fetch:status-changed', listener)
    },
  },
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)

// --------- Preload scripts loading ---------
function domReady(condition: DocumentReadyState[] = ['complete', 'interactive']) {
  return new Promise(resolve => {
    if (condition.includes(document.readyState)) {
      resolve(true)
    } else {
      document.addEventListener('readystatechange', () => {
        if (condition.includes(document.readyState)) {
          resolve(true)
        }
      })
    }
  })
}

const safeDOM = {
  append(parent: HTMLElement, child: HTMLElement) {
    if (!Array.from(parent.children).find(e => e === child)) {
      return parent.appendChild(child)
    }
  },
  remove(parent: HTMLElement, child: HTMLElement) {
    if (Array.from(parent.children).find(e => e === child)) {
      return parent.removeChild(child)
    }
  },
}

/**
 * https://tobiasahlin.com/spinkit
 * https://connoratherton.com/loaders
 * https://projects.lukehaas.me/css-loaders
 * https://matejkustec.github.io/SpinThatShit
 */
function useLoading() {
  const className = `loaders-css__square-spin`
  const styleContent = `
@keyframes square-spin {
  25% { transform: perspective(100px) rotateX(180deg) rotateY(0); }
  50% { transform: perspective(100px) rotateX(180deg) rotateY(180deg); }
  75% { transform: perspective(100px) rotateX(0) rotateY(180deg); }
  100% { transform: perspective(100px) rotateX(0) rotateY(0); }
}
.${className} > div {
  animation-fill-mode: both;
  width: 50px;
  height: 50px;
  background: #fff;
  animation: square-spin 3s 0s cubic-bezier(0.09, 0.57, 0.49, 0.9) infinite;
}
.app-loading-wrap {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #282c34;
  z-index: 9;
}
    `
  const oStyle = document.createElement('style')
  const oDiv = document.createElement('div')

  oStyle.id = 'app-loading-style'
  oStyle.innerHTML = styleContent
  oDiv.className = 'app-loading-wrap'
  oDiv.innerHTML = `<div class="${className}"><div></div></div>`

  return {
    appendLoading() {
      safeDOM.append(document.head, oStyle)
      safeDOM.append(document.body, oDiv)
    },
    removeLoading() {
      safeDOM.remove(document.head, oStyle)
      safeDOM.remove(document.body, oDiv)
    },
  }
}

// ----------------------------------------------------------------------

const { appendLoading, removeLoading } = useLoading()
domReady().then(appendLoading)

window.onmessage = (ev) => {
  ev.data.payload === 'removeLoading' && removeLoading()
}

setTimeout(removeLoading, 4999)
