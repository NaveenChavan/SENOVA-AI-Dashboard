import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'

import Upload from '../pages/Upload'
import InvoiceTotalWarningModal from '../components/upload/InvoiceTotalWarningModal'
import useSalesStore from '../store/useSalesStore'
import api from '../services/api'

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn().mockResolvedValue({ data: { ai_enabled: false } }),
  },
}))

// A 409 (requires_acknowledgement) axios-style error.
function warn409(warnings) {
  return {
    response: {
      status: 409,
      data: { detail: { message: 'Please confirm this mapping before proceeding.', warnings, requires_acknowledgement: true } },
    },
  }
}

// A 400 strong-evidence rejection axios-style error.
function reject400(message) {
  return { response: { status: 400, data: { detail: message } } }
}

const FILE_ID = 'f_mod24'
const MAPPING = { 'Sale Date': 'Date', 'Bill No': 'Invoice No', Amount: 'Line Total' }

function resetStore() {
  useSalesStore.setState({
    fileId: FILE_ID,
    isLoading: false,
    error: null,
    mappingPreview: null,
    mappingWarnings: [],
    pendingMapping: null,
    uploadErrors: [],
  })
}

describe('Module 2.4 — store: invoice-total warning handling', () => {
  beforeEach(() => {
    api.post.mockReset()
    resetStore()
  })

  it('a 409 advisory becomes a non-blocking warning, not an error', async () => {
    api.post.mockRejectedValueOnce(warn409(['Amount is the same on every line of the only invoice.']))

    const res = await useSalesStore.getState().confirmMapping(FILE_ID, MAPPING)

    expect(res).toBeNull()
    const s = useSalesStore.getState()
    expect(s.error).toBeNull()                    // NOT surfaced as a red error
    expect(s.mappingWarnings.length).toBe(1)
    expect(s.pendingMapping).toEqual({ mapping: MAPPING, userSelectedColumns: [], rememberMapping: false })
    expect(s.mappingPreview).toBeNull()           // preview untouched by this path
  })

  it('acknowledging retries with acknowledge_warnings=true and clears the warning', async () => {
    api.post.mockRejectedValueOnce(warn409(['maybe an invoice total']))
    await useSalesStore.getState().confirmMapping(FILE_ID, MAPPING)

    api.post.mockResolvedValueOnce({ data: { valid_count: 5, warnings: ['maybe an invoice total'], errors: [], date_range: {}, optional_fields: [] } })
    const res = await useSalesStore.getState().acknowledgeMappingWarnings()

    expect(res.valid_count).toBe(5)
    // Second call must carry acknowledge_warnings: true and the SAME mapping.
    const lastCall = api.post.mock.calls.at(-1)
    expect(lastCall[0]).toBe(`/upload/${FILE_ID}/confirm-mapping`)
    expect(lastCall[1].acknowledge_warnings).toBe(true)
    expect(lastCall[1].mapping).toEqual(MAPPING)
    expect(useSalesStore.getState().mappingWarnings).toEqual([])
    expect(useSalesStore.getState().pendingMapping).toBeNull()
  })

  it('dismissing returns to the mapping screen without losing fileId', () => {
    useSalesStore.setState({ mappingWarnings: ['w'], pendingMapping: { mapping: MAPPING, userSelectedColumns: [], rememberMapping: false } })
    useSalesStore.getState().dismissMappingWarnings()
    const s = useSalesStore.getState()
    expect(s.mappingWarnings).toEqual([])
    expect(s.pendingMapping).toBeNull()
    expect(s.fileId).toBe(FILE_ID)                // file + mapping selections preserved
  })

  it('a 400 strong-evidence rejection stays a blocking error and is never a warning', async () => {
    api.post.mockRejectedValueOnce(reject400("'Amount' looks like an invoice-level total..."))

    await expect(useSalesStore.getState().confirmMapping(FILE_ID, MAPPING)).rejects.toBeTruthy()

    const s = useSalesStore.getState()
    expect(s.error).toMatch(/invoice-level total/i)
    expect(s.mappingWarnings).toEqual([])         // NOT downgraded to a warning
    expect(s.pendingMapping).toBeNull()
  })

  it('prevents duplicate submissions while a request is in flight', async () => {
    let resolveFirst
    api.post.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))

    const p1 = useSalesStore.getState().confirmMapping(FILE_ID, MAPPING)   // in flight
    const p2 = useSalesStore.getState().confirmMapping(FILE_ID, MAPPING)   // should be ignored

    expect(await p2).toBeNull()                   // second call short-circuits
    expect(api.post).toHaveBeenCalledTimes(1)     // only one network call

    resolveFirst({ data: { valid_count: 5, warnings: [], errors: [], date_range: {}, optional_fields: [] } })
    await p1
    expect(api.post).toHaveBeenCalledTimes(1)
  })
})

describe('Module 2.4 — InvoiceTotalWarningModal (accessibility + actions)', () => {
  it('renders an accessible dialog with both actions and the warnings', () => {
    const onGoBack = vi.fn()
    const onAcknowledge = vi.fn()
    render(
      <InvoiceTotalWarningModal
        open
        warnings={['Amount is the same on every line of the only invoice.']}
        onGoBack={onGoBack}
        onAcknowledge={onAcknowledge}
      />
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(screen.getByTestId('invoice-total-warning-list').textContent).toMatch(/every line/i)

    fireEvent.click(screen.getByRole('button', { name: /Go back and change mapping/i }))
    expect(onGoBack).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Acknowledge and proceed/i }))
    expect(onAcknowledge).toHaveBeenCalled()
  })

  it('disables both actions while a retry is submitting (no duplicate submit)', () => {
    const onAcknowledge = vi.fn()
    const onGoBack = vi.fn()
    render(
      <InvoiceTotalWarningModal open warnings={['w']} onGoBack={onGoBack} onAcknowledge={onAcknowledge} submitting />
    )
    // While submitting, the primary button shows the loading state (label "Loading…")
    // and both actions are disabled so a second submit cannot be fired.
    const buttons = screen.getAllByRole('button')
    expect(buttons.every((b) => b.disabled)).toBe(true)
    const ack = screen.getByRole('button', { name: /Loading/i })
    fireEvent.click(ack)
    expect(onAcknowledge).not.toHaveBeenCalled()
    const goBack = screen.getByRole('button', { name: /Go back and change mapping/i })
    fireEvent.click(goBack)
    expect(onGoBack).not.toHaveBeenCalled()
  })
})

describe('Module 2.4 — InvoiceTotalWarningModal (keyboard & focus accessibility)', () => {
  it('Escape dismisses the warning (equivalent to Go back) without acknowledging/submitting', () => {
    const onGoBack = vi.fn()
    const onAcknowledge = vi.fn()
    render(
      <InvoiceTotalWarningModal open warnings={['w']} onGoBack={onGoBack} onAcknowledge={onAcknowledge} />
    )

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' })
    expect(onGoBack).toHaveBeenCalledTimes(1)
    expect(onAcknowledge).not.toHaveBeenCalled()
  })

  it('moves focus into the dialog when it opens', () => {
    render(<InvoiceTotalWarningModal open warnings={['w']} onGoBack={vi.fn()} onAcknowledge={vi.fn()} />)

    const dialog = screen.getByRole('dialog')
    // Focus landed on a focusable element inside the dialog (the first button).
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(document.body)
  })

  it('Tab and Shift+Tab cannot move keyboard focus outside the dialog', () => {
    render(<InvoiceTotalWarningModal open warnings={['w']} onGoBack={vi.fn()} onAcknowledge={vi.fn()} />)

    const dialog = screen.getByRole('dialog')
    const focusables = Array.from(
      dialog.querySelectorAll('button:not([disabled]), a[href], input:not([disabled])')
    )
    expect(focusables.length).toBeGreaterThan(0)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    // Tab from the last focusable wraps back to the first (stays in dialog).
    last.focus()
    fireEvent.keyDown(window, { key: 'Tab', code: 'Tab' })
    expect(document.activeElement).toBe(first)
    expect(dialog.contains(document.activeElement)).toBe(true)

    // Shift+Tab from the first focusable wraps to the last (stays in dialog).
    first.focus()
    fireEvent.keyDown(window, { key: 'Tab', code: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
    expect(dialog.contains(document.activeElement)).toBe(true)

    // Focus escaping to the document body is pulled back into the dialog.
    document.body.focus()
    fireEvent.focusIn(document.body)
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it('restores focus to the triggering element when the dialog closes', () => {
    // A real trigger button that owns focus before the dialog opens.
    const trigger = document.createElement('button')
    trigger.textContent = 'Confirm & analyse'
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const { rerender } = render(
      <InvoiceTotalWarningModal open warnings={['w']} onGoBack={vi.fn()} onAcknowledge={vi.fn()} />
    )
    // Dialog took focus.
    expect(document.activeElement).not.toBe(trigger)

    // Close the dialog — focus returns to the opener.
    rerender(
      <InvoiceTotalWarningModal open={false} warnings={['w']} onGoBack={vi.fn()} onAcknowledge={vi.fn()} />
    )
    expect(document.activeElement).toBe(trigger)

    document.body.removeChild(trigger)
  })

  it('Escape does not interrupt an in-flight acknowledgement (submitting)', () => {
    const onGoBack = vi.fn()
    const onAcknowledge = vi.fn()
    render(
      <InvoiceTotalWarningModal open warnings={['w']} onGoBack={onGoBack} onAcknowledge={onAcknowledge} submitting />
    )

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' })
    // Neither dismissal nor acknowledgement fires while the request is in flight.
    expect(onGoBack).not.toHaveBeenCalled()
    expect(onAcknowledge).not.toHaveBeenCalled()
    // Dialog stays open so the running request is not torn down under it.
    expect(screen.getByRole('dialog')).toBeTruthy()
  })
})

describe('Module 2.4 — Upload page shows the warning dialog', () => {
  beforeEach(() => {
    api.post.mockReset()
    useSalesStore.setState({
      fetchAiCapabilities: vi.fn(),
      fileId: FILE_ID,
      mappingPreview: null,
      isLoading: false,
      error: null,
      mappingWarnings: [],
      pendingMapping: null,
      aiConsentAnswer: true,
      aiConsent: true,
      aiAvailable: false,
      pipelineTimings: null,
    })
  })

  it('opens the warning modal when the store holds mapping warnings', () => {
    useSalesStore.setState({
      mappingPreview: {
        file_id: FILE_ID, filename: 'f.csv', row_count: 5, required_fields: ['Date'],
        optional_fields: [], field_help: {}, sample_rows: [], ai_enabled: false,
        pipeline_timings: { total_ms: 1 }, detected_columns: [],
      },
      mappingWarnings: ['This amount might be an invoice-level total.'],
      pendingMapping: { mapping: MAPPING, userSelectedColumns: [], rememberMapping: false },
    })

    render(
      <HelmetProvider>
        <MemoryRouter>
          <Upload />
        </MemoryRouter>
      </HelmetProvider>
    )

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Acknowledge and proceed/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Go back and change mapping/i })).toBeTruthy()
  })

  it('Go back closes the warning and keeps the mapping screen (selections preserved)', async () => {
    useSalesStore.setState({
      mappingPreview: {
        file_id: FILE_ID, filename: 'f.csv', row_count: 5, required_fields: ['Date'],
        optional_fields: [], field_help: {}, sample_rows: [], ai_enabled: false,
        pipeline_timings: { total_ms: 1 }, detected_columns: [],
      },
      mappingWarnings: ['This amount might be an invoice-level total.'],
      pendingMapping: { mapping: MAPPING, userSelectedColumns: [], rememberMapping: false },
    })

    render(
      <HelmetProvider>
        <MemoryRouter>
          <Upload />
        </MemoryRouter>
      </HelmetProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: /Go back and change mapping/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // Mapping screen is still mounted (fileId + preview preserved).
    expect(useSalesStore.getState().mappingPreview).not.toBeNull()
    expect(useSalesStore.getState().fileId).toBe(FILE_ID)
  })
})
