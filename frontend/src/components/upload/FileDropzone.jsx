import { useCallback, useRef, useState } from 'react'
import Button from '../common/Button'

function generateTemplate() {
  const header = 'Date,Category,Item,Quantity,Selling Price,Cost Price\n'
  const rows = [
    '01-01-2025,Electronics,Wireless Mouse,15,1200.00,800.00',
    '02-01-2025,Clothing,Cotton T-Shirt,30,599.00,350.00',
    '03-01-2025,Home Appliances,Desk Lamp,10,2499.00,1800.00',
    '04-01-2025,Electronics,USB-C Hub,20,1799.00,1200.00',
    '05-01-2025,Clothing,Denim Jacket,8,2999.00,2000.00',
  ].join('\n')
  return header + rows
}

function downloadTemplate() {
  const csv = generateTemplate()
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'senova_template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export default function FileDropzone({ onFileSelected, disabled, progressMessage }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [fileError, setFileError] = useState('')

  const handleFile = useCallback(
    (file) => {
      if (!file) return
      const allowed = ['.csv', '.xlsx']
      const ext = '.' + file.name.split('.').pop().toLowerCase()
      if (!allowed.includes(ext)) {
        setFileError('Unsupported file type. Please upload a .csv or .xlsx file.')
        return
      }
      setFileError('')
      onFileSelected(file)
    },
    [onFileSelected],
  )

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragging(false)
      handleFile(e.dataTransfer.files[0])
    },
    [handleFile],
  )

  const onDragOver = (e) => {
    e.preventDefault()
    setDragging(true)
  }
  const onDragLeave = () => setDragging(false)

  return (
    <div>
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload a CSV or Excel file"
        onKeyDown={(e) => {
          if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        className={`card-gradient border-2 border-dashed rounded-xl p-6 sm:p-12 text-center cursor-pointer transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-emerald-400/50 ${
          dragging
            ? 'border-emerald-400 bg-emerald-400/5 shadow-lg shadow-emerald-500/10'
            : 'border-slate-600 hover:border-emerald-500/50 hover:bg-slate-800/50'
        } ${disabled ? 'opacity-60 pointer-events-none' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          hidden
          onChange={(e) => handleFile(e.target.files[0])}
          disabled={disabled}
        />

        <div className="flex flex-col items-center gap-3">
          <div className={`p-3 rounded-full ${dragging ? 'bg-emerald-400/10' : 'bg-slate-700/50'}`}>
            <svg className={`w-8 h-8 sm:w-10 sm:h-10 ${dragging ? 'text-emerald-400' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <p className="text-slate-200 font-medium text-sm sm:text-base">Drop your CSV / Excel file here, or click to browse</p>
          <p className="text-xs sm:text-sm text-slate-500">Expected columns: Date, Category, Item, Quantity, Selling Price, Cost Price</p>

          {progressMessage ? (
            <div className="flex items-center gap-2 mt-2">
              <svg className="animate-spin h-4 w-4 text-emerald-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-emerald-400 text-sm font-medium">{progressMessage}</span>
            </div>
          ) : null}
        </div>

        {!disabled && !progressMessage && (
          <div className="mt-6">
            <Button type="button" variant="secondary">Choose File</Button>
          </div>
        )}
      </div>

      {fileError && (
        <p className="mt-3 text-sm text-red-400 text-center" role="alert">
          {fileError}
        </p>
      )}

      <div className="mt-4 text-center">
        <button
          type="button"
          onClick={downloadTemplate}
          className="min-h-[44px] text-sm text-slate-500 hover:text-emerald-400 transition-colors underline underline-offset-2 decoration-slate-600 hover:decoration-emerald-400"
        >
          Download Standard Format (.csv)
        </button>
      </div>
    </div>
  )
}
