import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import useSalesStore from '../store/useSalesStore'
import FileDropzone from '../components/upload/FileDropzone'
import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import RowErrorsBanner from '../components/dashboard/RowErrorsBanner'

export default function Upload() {
  const navigate = useNavigate()
  const {
    uploadFile,
    confirmMapping,
    cancelMapping,
    mappingPreview,
    isLoading,
    validationMessage,
    error,
    uploadErrors,
  } = useSalesStore()
  const [uploadDone, setUploadDone] = useState(false)

  const handleFile = async (file) => {
    setUploadDone(false)
    try {
      // Step 1: upload the file — this only returns a column-mapping
      // preview. We don't know if the data is "good" yet; that's decided
      // after the user confirms their mapping below.
      await uploadFile(file)
    } catch {
      // Error is already stored in Zustand.
    }
  }

  const handleConfirmMapping = async (mapping) => {
    const fileId = useSalesStore.getState().fileId
    try {
      const res = await confirmMapping(fileId, mapping)
      setUploadDone(true)
      if (res.valid_count > 0) {
        navigate(`/dashboard?fileId=${fileId}`)
      }
    } catch {
      // Error is already stored in Zustand; stays on this page to show it.
    }
  }

  // While the mapping screen is showing, hide the dropzone + intro copy —
  // the mapping table is the full-width focus of the page at this step.
  if (mappingPreview) {
    return (
      <section className="max-w-4xl mx-auto pt-4 sm:pt-8">
        <Helmet>
          <title>Confirm Columns — SENOVA AI Dashboard</title>
        </Helmet>
        <ColumnMappingScreen
          preview={mappingPreview}
          onConfirm={handleConfirmMapping}
          onCancel={cancelMapping}
          submitting={isLoading}
        />
        {error && (
          <div className="mt-4 card-gradient rounded-xl px-4 sm:px-5 py-3 flex items-start gap-3" style={{ border: '1px solid rgba(239,68,68,0.3)' }}>
            <svg className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--accent-red)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm" style={{ color: 'var(--accent-red)' }}>{error}</p>
          </div>
        )}
      </section>
    )
  }

  return (
    <section className="max-w-2xl mx-auto pt-4 sm:pt-8 px-0">
      <Helmet>
        <title>Upload Data — SENOVA AI Dashboard | Retail & MSME Analytics</title>
        <meta name="description" content="Upload your CSV or Excel sales data to generate AI-powered retail analytics, category breakdowns, dead stock reports, and daily sales trends." />
      </Helmet>

      <div className="text-center mb-8 sm:mb-12">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold mb-6"
          style={{
            background: 'var(--accent-blue-glow)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--accent-blue)'
          }}>
          <span className="w-1.5 h-1.5 rounded-full inline-block animate-pulse" style={{ background: 'var(--accent-blue)' }} />
          AI-Powered Analytics Engine
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold mb-3" style={{color: 'var(--text-primary)'}}>
          Upload Your Sales Data
        </h1>
        <p className="text-sm sm:text-base max-w-lg mx-auto" style={{color: 'var(--text-secondary)'}}>
          Drop your daily sales CSV or Excel file — any column layout works.
          You'll confirm your columns next, then SENOVA validates every row and
          generates an instant retail intelligence dashboard.
        </p>
      </div>

      <FileDropzone
        onFileSelected={handleFile}
        disabled={isLoading}
        progressMessage={validationMessage}
      />

      <div className="mt-6 space-y-4">
        {error && (
          <div className="card-gradient rounded-xl px-4 sm:px-5 py-3 flex items-start gap-3" style={{ border: '1px solid rgba(239,68,68,0.3)' }}>
            <svg className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--accent-red)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm" style={{ color: 'var(--accent-red)' }}>{error}</p>
          </div>
        )}

        {uploadDone && !isLoading && uploadErrors.length > 0 && (
          <RowErrorsBanner errors={uploadErrors} />
        )}

        {uploadDone && !isLoading && uploadErrors.length === 0 && !error && (
          <div className="card-gradient rounded-xl px-4 sm:px-5 py-3 flex items-center gap-3" style={{ border: '1px solid rgba(5,150,105,0.3)' }}>
            <svg className="w-5 h-5 shrink-0" style={{ color: 'var(--accent-green)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-sm font-medium" style={{ color: 'var(--accent-green)' }}>
              All rows validated successfully. Redirecting to dashboard...
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
