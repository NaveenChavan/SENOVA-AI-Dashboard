import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'motion/react'

import useSalesStore from '../store/useSalesStore'
import FileDropzone from '../components/upload/FileDropzone'
import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import RowErrorsBanner from '../components/dashboard/RowErrorsBanner'
import Icon from '../components/common/Icon'

// Minimum visible duration for each step (ms)
const MIN_STEP_DURATION = 600
// Extra delay after step 4 becomes active before navigation (ms)
const STEP4_HOLD_DURATION = 700

/**
 * Upload page — two steps in one route.
 *
 * Step 1 is a compact hero plus the dropzone, sized to fit a phone screen
 * without scrolling. Step 2 replaces the whole page with the column-mapping
 * table, because confirming the mapping is the only task at that point.
 *
 * A pipeline stepper sits above both steps so the user always knows where
 * they are in Upload → Confirm columns → Validate rows → Build dashboard.
 * Its active step is derived from real store state (mappingPreview,
 * isLoading, uploadDone) — never a separate, fakeable progress value.
 */

const EASE = [0.16, 1, 0.3, 1]

const PIPELINE_STEPS = [
  { key: 'upload', label: 'Upload' },
  { key: 'confirm', label: 'Confirm columns' },
  { key: 'validate', label: 'Validate rows' },
  { key: 'build', label: 'Build dashboard' },
]

function PipelineStepper({ activeIndex }) {
  return (
    <nav aria-label="Upload progress" className="mb-6">
      <ol className="flex items-center justify-center gap-1.5 sm:gap-2">
        {PIPELINE_STEPS.map((step, i) => {
          const done = i < activeIndex
          const current = i === activeIndex
          return (
            <li key={step.key} className="flex items-center gap-1.5 sm:gap-2">
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="flex items-center justify-center rounded-full text-[11px] font-bold shrink-0"
                  style={{
                    width: 22,
                    height: 22,
                    background: done || current ? 'var(--gradient-accent)' : 'var(--bg-input)',
                    color: done || current ? '#ffffff' : 'var(--text-muted)',
                    boxShadow: current ? 'var(--shadow-glow)' : 'none',
                  }}
                  animate={current ? { scale: [1, 1.08, 1] } : { scale: 1 }}
                  transition={current ? { duration: 1.6, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.2 }}
                >
                  {done ? <Icon name="check" className="w-3 h-3" /> : i + 1}
                </motion.span>
                <span
                  className="text-[12px] font-medium hidden sm:inline"
                  style={{ color: current ? 'var(--text-primary)' : 'var(--text-muted)' }}
                >
                  {step.label}
                </span>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <span
                  aria-hidden="true"
                  className="w-4 sm:w-6 h-px shrink-0"
                  style={{ background: done ? 'var(--accent-blue)' : 'var(--border-subtle)' }}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

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
  const validateStartRef = useRef(null)

  const handleFile = async (file) => {
    setUploadDone(false)
    validateStartRef.current = null
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
    validateStartRef.current = Date.now()
    try {
      const response = await confirmMapping(fileId, mapping)
      // Ensure minimum visible duration for "Validate rows" step (step 3)
      const elapsed = Date.now() - validateStartRef.current
      if (elapsed < MIN_STEP_DURATION) {
        await new Promise(resolve => setTimeout(resolve, MIN_STEP_DURATION - elapsed))
      }
      setUploadDone(true)
      // Hold step 4 ("Build dashboard") visibly before navigating
      await new Promise(resolve => setTimeout(resolve, STEP4_HOLD_DURATION))
      if (response.valid_count > 0) navigate(`/dashboard?fileId=${fileId}`)
    } catch {
      // Error already stored; stay on this page to show it.
    }
  }

  // Real pipeline position: 0 while choosing a file, 1 once mapping is shown,
  // 2 while confirm-mapping is in flight (validating rows), 3 once done and
  // about to navigate into the built dashboard.
  const activeIndex = uploadDone ? 3 : mappingPreview ? (isLoading ? 2 : 1) : 0

  // ── Step 2: mapping confirmation ─────────────────────────────────────
  if (mappingPreview) {
    return (
      <section className="mx-auto w-full" style={{ maxWidth: 900 }}>
        <Helmet>
          <title>Confirm Columns — SENOVA AI Dashboard</title>
        </Helmet>

        <PipelineStepper activeIndex={activeIndex} />

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

      <PipelineStepper activeIndex={activeIndex} />

      <motion.div
        className="text-center mb-4"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE }}
      >
        <span className="badge-glow mb-3 px-3" style={{ height: 26 }}>
          <Icon name="spark" className="w-3 h-3" />
          Computed analytics engine
        </span>

        <h1 className="text-display text-xl mb-1.5">Upload your sales data</h1>
        <p className="text-xs mx-auto" style={{ color: 'var(--text-secondary)', maxWidth: 420 }}>
          Drop your daily sales CSV or Excel file — any column layout works. You'll confirm your columns next, then
          SENOVA validates every row and builds the dashboard.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, delay: 0.1, ease: EASE }}
      >
        <FileDropzone onFileSelected={handleFile} disabled={isLoading} progressMessage={validationMessage} />
      </motion.div>

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
