import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { attachmentContentUrl, uploadAttachment } from '../api/client'
import type { Attachment } from '../api/types'

type Props = {
  attachments: Attachment[]
  onAttachmentsChange: (attachments: Attachment[]) => void
  onIntentChange: (intent: string) => void
}

const imageIntents = ['Use this as UI reference', 'Find bug in screenshot', 'Recreate this layout', 'Explain what is wrong']

export function AttachmentDropzone({ attachments, onAttachmentsChange, onIntentChange }: Props) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files)
      if (!list.length) return
      setUploading(true)
      try {
        const uploaded = []
        for (const file of list) {
          uploaded.push(await uploadAttachment(file))
        }
        onAttachmentsChange([...attachments, ...uploaded])
      } finally {
        setUploading(false)
      }
    },
    [attachments, onAttachmentsChange],
  )

  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const files = event.clipboardData?.files
      if (files?.length) void uploadFiles(files)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [uploadFiles])

  const hasImages = useMemo(() => attachments.some((item) => item.content_type.startsWith('image/')), [attachments])

  return (
    <section
      className={`dropzone ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        void uploadFiles(event.dataTransfer.files)
      }}
    >
      <input ref={inputRef} type="file" multiple hidden onChange={(event) => event.target.files && uploadFiles(event.target.files)} />
      <div className="dropzone-head">
        <div>
          <strong>Drop files, screenshots, or specs</strong>
          <span>Paste an image, drag a folder artifact, or browse for context.</span>
        </div>
        <button className="ghost-button" type="button" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? 'Uploading...' : 'Browse'}
        </button>
      </div>
      {hasImages && (
        <div className="intent-chips" aria-label="Image intent shortcuts">
          {imageIntents.map((intent) => (
            <button key={intent} type="button" onClick={() => onIntentChange(intent)}>
              {intent}
            </button>
          ))}
        </div>
      )}
      <div className="attachment-grid">
        {attachments.map((attachment) => (
          <article key={attachment.id} className="attachment-card">
            {attachment.content_type.startsWith('image/') ? (
              <img src={attachmentContentUrl(attachment.id)} alt={attachment.filename} />
            ) : (
              <div className="file-glyph">{attachment.filename.split('.').pop()?.slice(0, 4) || 'file'}</div>
            )}
            <div>
              <strong>{attachment.filename}</strong>
              <span>{Math.ceil(attachment.size_bytes / 1024)} KB · {attachment.analysis_status}</span>
            </div>
            <button
              type="button"
              aria-label={`Remove ${attachment.filename}`}
              onClick={() => onAttachmentsChange(attachments.filter((item) => item.id !== attachment.id))}
            >
              ×
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}
