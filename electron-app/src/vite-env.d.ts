/// <reference types="vite/client" />

import type { ElectronAPI } from './shared/ipc'

interface Window {
  electronAPI: ElectronAPI
}
