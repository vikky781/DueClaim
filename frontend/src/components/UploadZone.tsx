import { useRef, useState, type DragEvent } from 'react'

import { api } from '../api/client'
import type { ExtractionResponse } from '../api/types'
import { Eyebrow } from './ui'

const ACCEPT = ['image/jpeg', 'image/png', 'application/pdf']
const MAX_BYTES = 10 * 1024 * 1024
const EXTRACT_TIMEOUT_MS = 30_000

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading'; name: string }
  | { kind: 'extracting'; name: string }
  | { kind: 'done'; name: string; filled: number; total: number }
  | { kind: 'failed'; name: string; message: string }

interface Props {
  /** Called with Textract's proposal. The form decides what to do with it. */
  onExtracted: (result: ExtractionResponse) => number
}

/**
 * The OCR accelerator. Pick a file -> presign -> PUT straight to S3 -> extract.
 * Every failure is a message here and nothing more: the manual form below is
 * always the product; this only saves typing.
 */
export default function UploadZone({ onExtracted }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const busy = phase.kind === 'uploading' || phase.kind === 'extracting'

  async function handleFile(file: File) {
    if (!ACCEPT.includes(file.type)) {
      setPhase({ kind: 'failed', name: file.name, message: 'Use a JPEG, PNG or single-page PDF.' })
      return
    }
    if (file.size > MAX_BYTES) {
      setPhase({ kind: 'failed', name: file.name, message: 'That file is over 10 MB. Try a smaller scan.' })
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), EXTRACT_TIMEOUT_MS)
    try {
      setPhase({ kind: 'uploading', name: file.name })
      const presign = await api.presignUpload(file.type, file.name)
      await api.uploadToS3(presign, file, controller.signal)
      setPhase({ kind: 'extracting', name: file.name })
      const result = await api.extractUpload(presign.key, controller.signal)
      const filled = onExtracted(result)
      setPhase({ kind: 'done', name: file.name, filled, total: 4 })
    } catch (err) {
      const message = controller.signal.aborted
        ? 'Reading the invoice took too long. Fill the form in by hand — nothing you typed was lost.'
        : `${err instanceof Error ? err.message : 'Extraction failed.'} Fill the form in by hand — nothing you typed was lost.`
      setPhase({ kind: 'failed', name: file.name, message })
    } finally {
      clearTimeout(timer)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragging(false)
    if (busy) return
    const file = e.dataTransfer.files?.[0]
    if (file) void handleFile(file)
  }

  return (
    <section aria-labelledby="upload-heading" className="mb-10">
      <div className="flex items-baseline justify-between">
        <Eyebrow>
          <h2 id="upload-heading" className="inline">
            Start from the invoice
          </h2>
        </Eyebrow>
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-mute">optional</span>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          if (!busy) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-3 rounded-md border border-dashed px-5 py-6 transition-colors ${
          dragging ? 'border-brass bg-slate' : 'border-rule'
        }`}
      >
        <input
          ref={inputRef}
          id="invoice-file"
          type="file"
          accept={ACCEPT.join(',')}
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleFile(file)
          }}
        />

        {phase.kind === 'idle' && (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-[15px] text-mute">
              Drop a photo or PDF of the invoice here and we’ll read the number, date, buyer and total for you to
              check.
            </p>
            <label
              htmlFor="invoice-file"
              className="inline-flex cursor-pointer items-center rounded-md border border-rule px-4 py-2 text-[15px] font-medium text-paper transition-colors hover:border-mute hover:bg-slate"
            >
              Choose file
            </label>
          </div>
        )}

        {busy && (
          <div className="flex items-center gap-3 font-mono text-[13px] text-mute" role="status" aria-live="polite">
            <span aria-hidden="true" className="inline-block size-2 rounded-full bg-brass animate-pulse-dot" />
            {phase.kind === 'uploading' ? 'Uploading' : 'Reading'} <span className="text-paper">{phase.name}</span>…
          </div>
        )}

        {phase.kind === 'done' && (
          <div className="flex flex-wrap items-center justify-between gap-4" role="status" aria-live="polite">
            <p className="text-[15px]">
              <span className="text-paper">
                Read {phase.filled} of {phase.total} fields
              </span>{' '}
              <span className="text-mute">
                from {phase.name}. Check each one below — anything marked{' '}
                <span className="text-brass">check this</span> was read with low confidence.
              </span>
            </p>
            <label htmlFor="invoice-file" className="cursor-pointer text-[14px] text-brass hover:text-paper">
              Try another file
            </label>
          </div>
        )}

        {phase.kind === 'failed' && (
          <div className="flex flex-wrap items-center justify-between gap-4" role="alert">
            <p className="text-[15px]">
              <span className="text-alert">Couldn’t read {phase.name}.</span>{' '}
              <span className="text-mute">{phase.message}</span>
            </p>
            <label htmlFor="invoice-file" className="cursor-pointer text-[14px] text-brass hover:text-paper">
              Try again
            </label>
          </div>
        )}
      </div>
    </section>
  )
}
