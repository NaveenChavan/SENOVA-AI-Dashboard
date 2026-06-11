import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import useSalesStore from '../store/useSalesStore'
import FileDropzone from '../components/upload/FileDropzone'
import RowErrorsBanner from '../components/dashboard/RowErrorsBanner'

export default function Upload() {
  const navigate = useNavigate()
  const { uploadFile, isLoading, validationMessage, error, uploadErrors } = useSalesStore()
  const [uploadDone, setUploadDone] = useState(false)

  const handleFile = async (file) => {
    try {
      const res = await uploadFile(file)
      setUploadDone(true)
      if (res.valid_count > 0) {
        navigate(`/dashboard?fileId=${res.file_id}`)
      }
    } catch {
      // Error is already stored in Zustand.
    }
  }

  return (
    <section className="max-w-2xl mx-auto pt-4 sm:pt-8 px-0">
      <Helmet>
        <title>Upload Data — SENOVA AI Dashboard | Retail & MSME Analytics</title>
        <meta name="description" content="Upload your CSV or Excel sales data to generate AI-powered retail analytics, category breakdowns, dead stock reports, and daily sales trends." />
      </Helmet>

      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold mb-6"
          style={{
            background: 'rgba(56,189,248,0.08)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--accent-blue)'
          }}>
          <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse inline-block"/>
          AI-Powered Analytics Engine
        </div>
        <h1 className="text-4xl font-bold mb-3" style={{color: 'var(--text-primary)'}}>
          Upload Your Sales Data
        </h1>
        <p className="text-base max-w-lg mx-auto" style={{color: 'var(--text-secondary)'}}>
          Drop your daily sales CSV or Excel file. SENOVA validates every row and
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
          <div className="card-gradient border border-red-500/30 rounded-xl px-4 sm:px-5 py-3 flex items-start gap-3">
            <svg className="w-5 h-5 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        )}

        {uploadDone && !isLoading && uploadErrors.length > 0 && (
          <RowErrorsBanner errors={uploadErrors} />
        )}

        {uploadDone && !isLoading && uploadErrors.length === 0 && !error && (
          <div className="card-gradient border border-emerald-500/30 rounded-xl px-4 sm:px-5 py-3 flex items-center gap-3">
            <svg className="w-5 h-5 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-emerald-300 text-sm font-medium">
              All rows validated successfully. Redirecting to dashboard...
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
