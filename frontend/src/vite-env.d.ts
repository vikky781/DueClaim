/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the deployed API, e.g. https://xxxx.execute-api.ap-south-1.amazonaws.com (no trailing slash). */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
