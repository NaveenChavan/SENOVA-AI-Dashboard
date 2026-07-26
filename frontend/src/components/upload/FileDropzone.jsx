import { useCallback, useRef, useState } from 'react'

import Icon from '../common/Icon'

/**
 * File dropzone.
 *
 * Compact by design: a 140px drop target with one line of instruction and one
 * line of reassurance, so the upload page fits on a phone screen without
 * scrolling. The template download sits underneath as a text link rather than a
 * second button competing with the primary action.
 */

function buildTemplate() {
  const header = 'Date,Category,Item,Quantity,Selling Price,Cost Price,Discount,Branch,Payment Mode,Closing Stock\n'
  const rows = [
    '01-01-2026,Kurta,Cotton Kurta,15,750.00,300.00,0,MG Road,UPI,40',
    '02-01-2026,Saree,Silk Saree,3,3200.00,1800.00,100,MG Road,Card,12',
    '03-01-2026,Shirt,Formal Shirt,8,900.00,420.00,50,Station Road,Cash,25',
    '04-01-2026,Jeans,Denim Jeans,6,1500.00,700.00,0,Station Road,UPI,18',
    '05-01-2026,Kurta,Cotton Kurta,11,750.00,300.00,75,MG Road,Cash,29',
  ].join('\n')
  return header + rows
}

function downloadTemplate() {
  const blob = new Blob([buildTemplate()], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'senova_template.csv'
  link.click()
  URL.revokeObjectURL(url)
}

export default function FileDropzone({ onFileSelected, disabled, progressMessage }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [fileError, setFileError] = useState('')

  const handleFile = useCallback(
    (file) => {
      if (!file) return
      const extension = `.${file.name.split('.').pop().toLowerCase()}`
      if (!['.csv', '.xlsx'].includes(extension)) {
        setFileError('Unsupported file type. Please upload a .csv or .xlsx file.')
        return
      }
      setFileError('')
      onFileSelected(file)
    },
    [onFileSelected],
  )

  return (
    <div>
      <div
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          handleFile(event.dataTransfer.files[0])
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (!disabled && (event.key === 'Enter' || event.key === ' ')) {
            event.preventDefault()
            inputRef.current?.click()
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload a CSV or Excel file"
        aria-disabled={disabled || undefined}
        className={`card flex flex-col items-center justify-center text-center gap-2 cursor-pointer ${
          disabled ? 'opacity-60 pointer-events-none' : ''
        }`}
        style={{
          minHeight: 148,
          padding: 20,
          borderStyle: 'dashed',
          borderWidth: 2,
          borderColor: dragging ? 'var(--accent-blue)' : 'var(--border-strong)',
          background: dragging ? 'var(--accent-blue-glow)' : 'var(--bg-card)',
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          hidden
          onChange={(event) => handleFile(event.target.files[0])}
          disabled={disabled}
        />

        <span
          className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: dragging ? 'var(--bg-card)' : 'var(--bg-input)' }}
        >
          <Icon
            name="download"
            className="w-4 h-4"
            style={{ color: dragging ? 'var(--accent-blue)' : 'var(--text-muted)', transform: 'rotate(180deg)' }}
          />
        </span>

        <p className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          Drop your CSV / Excel file here, or click to browse
        </p>
        <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
          Any column layout works — you'll confirm your columns next.
        </p>

        {progressMessage && (
          <span className="inline-flex items-center gap-1.5 text-[12px] font-medium" style={{ color: 'var(--accent-blue)' }}>
            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {progressMessage}
          </span>
        )}
      </div>

      {fileError && (
        <p className="note mt-2" data-tone="danger" role="alert">
          <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
          <span>{fileError}</span>
        </p>
      )}

      <p className="text-center mt-2.5">
        <button
          type="button"
          onClick={downloadTemplate}
          className="text-[12px] underline underline-offset-2 cursor-pointer"
          style={{ color: 'var(--text-muted)' }}
        >
          Download the sample format (.csv)
        </button>
      </p>
    </div>
  )
}
