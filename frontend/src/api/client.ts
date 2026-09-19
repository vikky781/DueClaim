/**
 * The one place the frontend talks to the API.
 *
 * Every request carries the Cognito ID token as `Authorization: Bearer …`
 * (the API Gateway JWT authorizer validates it). Failures surface as
 * ApiError with a `kind` the UI can branch on. No component calls fetch.
 */

import { fetchAuthSession } from 'aws-amplify/auth'

import type {
  Business,
  ExtractionResponse,
  InvoiceCreate,
  InvoiceDetail,
  InvoiceRead,
  InvoiceStatus,
  NoticeResponse,
  PortfolioSummary,
  PresignResponse,
} from './types'

export const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

export type ApiErrorKind = 'config' | 'network' | 'auth' | 'not_found' | 'validation' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  /** Server-provided detail: FastAPI's string, or its list of field errors. */
  readonly detail: unknown

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, detail: unknown = undefined) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.detail = detail
  }

  /** Field -> message map from a 422 body, when the server gave one. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    if (Array.isArray(this.detail)) {
      for (const item of this.detail as { loc?: unknown[]; msg?: string }[]) {
        const field = item.loc?.[item.loc.length - 1]
        if (typeof field === 'string' && item.msg) out[field] = item.msg
      }
    }
    return out
  }
}

async function idToken(): Promise<string> {
  const session = await fetchAuthSession()
  const token = session.tokens?.idToken?.toString()
  if (!token) throw new ApiError('auth', 'Your session has expired. Sign in again.', 401)
  return token
}

function messageFor(status: number, detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (status === 422) return 'Some of the details were not accepted.'
  if (status === 404) return 'Not found.'
  return `The API answered ${status}.`
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  if (!API_URL) throw new ApiError('config', 'VITE_API_URL is not set.')
  const token = await idToken()

  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (err) {
    if (signal?.aborted) throw new ApiError('network', 'The request took too long and was cancelled.', null, err)
    throw new ApiError('network', `Couldn't reach the API at ${API_URL}.`, null, err)
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (res.ok) return data as T

  const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : data
  const kind: ApiErrorKind =
    res.status === 401 || res.status === 403
      ? 'auth'
      : res.status === 404
        ? 'not_found'
        : res.status === 422
          ? 'validation'
          : 'server'
  throw new ApiError(kind, messageFor(res.status, detail), res.status, detail)
}

const q = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams(Object.entries(params).filter((kv): kv is [string, string] => !!kv[1]))
  const str = s.toString()
  return str ? `?${str}` : ''
}

export const api = {
  /** null when the profile has not been created yet. */
  async getBusiness(): Promise<Business | null> {
    try {
      return await request<Business>('GET', '/api/v1/business')
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'not_found') return null
      throw err
    }
  },
  putBusiness: (b: Business) => request<Business>('POST', '/api/v1/business', b),

  listInvoices: () => request<InvoiceRead[]>('GET', '/api/v1/invoices'),
  getInvoice: (id: string, asOf?: string) =>
    request<InvoiceDetail>('GET', `/api/v1/invoices/${encodeURIComponent(id)}${q({ as_of: asOf })}`),
  createInvoice: (inv: InvoiceCreate) => request<InvoiceRead>('POST', '/api/v1/invoices', inv),
  patchInvoice: (id: string, patch: { amount_paid?: string; status?: InvoiceStatus }) =>
    request<InvoiceRead>('PATCH', `/api/v1/invoices/${encodeURIComponent(id)}`, patch),
  deleteInvoice: (id: string) => request<void>('DELETE', `/api/v1/invoices/${encodeURIComponent(id)}`),

  /** Generate the statutory demand notice PDF; returns a 1-hour presigned URL plus the figures used. */
  generateNotice: (id: string, asOf?: string) =>
    request<NoticeResponse>('POST', `/api/v1/invoices/${encodeURIComponent(id)}/notice${q({ as_of: asOf })}`),

  portfolioSummary: (asOf?: string) =>
    request<PortfolioSummary>('GET', `/api/v1/portfolio/summary${q({ as_of: asOf })}`),

  /* ---- OCR accelerator: presign -> PUT to S3 -> extract ---- */
  presignUpload: (contentType: string, filename?: string) =>
    request<PresignResponse>('POST', '/api/v1/uploads/presign', { content_type: contentType, filename }),

  /** Direct-to-S3 PUT using the presigned URL. No bearer token: the URL is the credential. */
  async uploadToS3(presign: PresignResponse, file: Blob, signal?: AbortSignal): Promise<void> {
    let res: Response
    try {
      res = await fetch(presign.url, { method: 'PUT', headers: presign.headers, body: file, signal })
    } catch (err) {
      throw new ApiError('network', 'The upload to storage failed before it completed.', null, err)
    }
    if (!res.ok) throw new ApiError('server', `Storage refused the upload (${res.status}).`, res.status)
  },

  extractUpload: (key: string, signal?: AbortSignal) =>
    request<ExtractionResponse>('POST', `/api/v1/uploads/${key}/extract`, undefined, signal),
}
