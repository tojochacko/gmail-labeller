import type { IpcRendererEvent } from 'electron'

window.ipcRenderer.on('main-process-message', (_event: IpcRendererEvent, ...args: unknown[]) => {
  console.log('[Receive Main-process message]:', ...args)
})
