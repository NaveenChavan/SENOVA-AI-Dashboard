import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
    <section className="max-w-2xl mx-auto pt-8">
      <div className="text-center mb-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-500/10 mb-4 glow-emerald">
          <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h1 className="text-3xl font-bold text-slate-100">Data Sync Portal</h1>
        <p className="text-slate-500 mt-2 max-w-md mx-auto">
          Upload your daily sales CSV or Excel file. We&apos;ll validate the schema and generate instant retail analytics.
        </p>
      </div>

      <FileDropzone
        onFileSelected={handleFile}
        disabled={isLoading}
        progressMessage={validationMessage}
      />

      <div className="mt-6 space-y-4">
        {error && (
          <div className="card-gradient border border-red-500/30 rounded-xl px-5 py-3 flex items-start gap-3">
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
          <div className="card-gradient border border-emerald-500/30 rounded-xl px-5 py-3 flex items-center gap-3">
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
