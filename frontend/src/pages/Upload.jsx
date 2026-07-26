import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

import useSalesStore from '../store/useSalesStore'
import FileDropzone from '../components/upload/FileDropzone'
import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import RowErrorsBanner from '../components/dashboard/RowErrorsBanner'
import Icon from '../components/common/Icon'

/**
 * Upload page — two steps in one route.
 *
 * Step 1 is a compact hero plus the dropzone, sized to fit a phone screen
 * without scrolling. Step 2 replaces the whole page with the column-mapping
 * table, because confirming the mapping is the only task at that point.
 */
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
      // Step 1 only returns a column-mapping preview; whether the data is
      // usable is decided after the user confirms the mapping.
      await uploadFile(file)
    } catch {
      // Error already stored in the store.
    }
  }

  const handleConfirmMapping = async (mapping) => {
    const fileId = useSalesStore.getState().fileId
    try {
      const response = await confirmMapping(fileId, mapping)
      setUploadDone(true)
      if (response.valid_count > 0) navigate(`/dashboard?fileId=${fileId}`)
    } catch {
      // Error already stored; stay on this page to show it.
    }
  }

  // ── Step 2: mapping confirmation ─────────────────────────────────────
  if (mappingPreview) {
    return (
      <section className="mx-auto w-full" style={{ maxWidth: 900 }}>
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
          <p className="note mt-3" data-tone="danger" role="alert">
            <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
            <span>{error}</span>
          </p>
        )}
      </section>
    )
  }

  // ── Step 1: choose a file ────────────────────────────────────────────
  return (
    <section className="mx-auto w-full" style={{ maxWidth: 560 }}>
      <Helmet>
        <title>Upload Data — SENOVA AI Dashboard | Retail &amp; MSME Analytics</title>
        <meta
          name="description"
          content="Upload your CSV or Excel sales data to generate AI-powered retail analytics, forecasts, reorder priorities and a CA-style financial report."
        />
      </Helmet>

      <div className="text-center mb-4">
        <span
          className="inline-flex items-center gap-1.5 rounded-full text-[12px] font-semibold mb-3 px-2.5"
          style={{
            height: 24,
            background: 'var(--accent-blue-glow)',
            color: 'var(--accent-blue)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <Icon name="spark" className="w-3 h-3" />
          Computed analytics engine
        </span>

        <h1 className="text-xl mb-1.5">Upload your sales data</h1>
        <p className="text-xs mx-auto" style={{ color: 'var(--text-secondary)', maxWidth: 420 }}>
          Drop your daily sales CSV or Excel file — any column layout works. You'll confirm your columns next, then
          SENOVA validates every row and builds the dashboard.
        </p>
      </div>

      <FileDropzone onFileSelected={handleFile} disabled={isLoading} progressMessage={validationMessage} />

      <div className="mt-3 space-y-2">
        {error && (
          <p className="note" data-tone="danger" role="alert">
            <Icon name="alert" className="w-4 h-4 shrink-0 mt-px" />
            <span>{error}</span>
          </p>
        )}

        {uploadDone && !isLoading && uploadErrors.length > 0 && <RowErrorsBanner errors={uploadErrors} />}

        {uploadDone && !isLoading && uploadErrors.length === 0 && !error && (
          <p className="note" data-tone="success">
            <Icon name="check" className="w-4 h-4 shrink-0 mt-px" />
            <span>All rows validated. Opening your dashboard…</span>
          </p>
        )}
      </div>
    </section>
  )
}
