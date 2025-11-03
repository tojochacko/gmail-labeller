/**
 * Type definitions for update component
 * Used for electron auto-updater functionality
 */

export interface VersionInfo {
  version: string;
  newVersion?: string;
  update?: boolean;
  releaseNotes?: string;
  downloadUrl?: string;
  releaseDate?: string;
}

export interface ErrorType {
  message: string;
  code?: string;
  stack?: string;
}
