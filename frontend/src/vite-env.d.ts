/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the deployed API, e.g. https://xxxx.execute-api.ap-south-1.amazonaws.com (no trailing slash). */
  readonly VITE_API_URL?: string
  /** Cognito User Pool id, e.g. ap-south-1_XXXXXXXXX (stack output UserPoolId). */
  readonly VITE_USER_POOL_ID?: string
  /** Cognito User Pool web client id (stack output UserPoolClientId). */
  readonly VITE_USER_POOL_CLIENT_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
