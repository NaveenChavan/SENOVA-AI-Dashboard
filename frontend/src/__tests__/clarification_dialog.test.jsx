import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'

import GroupedClarificationDialog from '../components/upload/GroupedClarificationDialog'
import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import Upload from '../pages/Upload'
import useSalesStore from '../store/useSalesStore'

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn().mockResolvedValue({ data: { ai_enabled: false } }),
  },
}))

const SAMPLE_AMBIGUOUS_COLUMNS = [
  {
    raw_column: 'Rate',
    suggested_field: null,
    confidence: 'fuzzy',
    confidence_score: 0.5,
    confidence_band: 'low',
    source: 'fallback',
    semantic_label: 'other',
    needs_review: true,
    recognised_unused: false,
    evidence_candidates: ['Selling Price', 'MRP', 'Cost Price'],
    evidence_reason: 'Header suggests a price, but no cross-check column was available to verify.',
    evidence_facts: [
      'Values are numeric and positive.',
      'Could be Selling Price, MRP, or Cost Price.',
    ],
  },
  {
    raw_column: 'Cust Name',
    suggested_field: null,
    confidence: 'fuzzy',
    confidence_score: 0.45,
    confidence_band: 'low',
    source: 'fallback',
    semantic_label: 'other',
    needs_review: true,
    recognised_unused: false,
    evidence_candidates: ['Customer', 'Item'],
    evidence_reason: 'Neighbouring columns do not clearly identify whether this is customer or item.',
    evidence_facts: ['No phone or SKU neighbours found.'],
  },
]

const SAMPLE_MASKED_ROWS = [
  {
    Rate: '₹ 250.00',
    'Cust Name': '[redacted]',
    'Bill Date': '2026-01-01',
    'Total Amt': '500.00',
  },
  {
    Rate: '₹ 1,200.00',
    'Cust Name': '[redacted]',
    'Bill Date': '2026-01-02',
    'Total Amt': '1200.00',
  },
]

describe('GroupedClarificationDialog (Module 2.2)', () => {
  it('renders a single grouped dialog containing all open ambiguous columns', () => {
    render(
      <GroupedClarificationDialog
        open
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Customer', 'Item', 'Line Total']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    // Single dialog element
    const dialogs = screen.getAllByRole('dialog')
    expect(dialogs).toHaveLength(1)
    expect(screen.getByText(/Clarify ambiguous columns/i)).toBeTruthy()

    // Both ambiguous columns are present in the same dialog
    expect(screen.getByTestId('clarification-card-Rate')).toBeTruthy()
    expect(screen.getByTestId('clarification-card-Cust Name')).toBeTruthy()
  })

  it('shows evidence-based candidates per column without forcing unjustified roles', () => {
    render(
      <GroupedClarificationDialog
        open
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Customer', 'Item', 'Line Total']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const rateCard = screen.getByTestId('clarification-card-Rate')
    expect(within(rateCard).getByRole('button', { name: /Selling Price/i })).toBeTruthy()
    expect(within(rateCard).getByRole('button', { name: /MRP/i })).toBeTruthy()
    expect(within(rateCard).getByRole('button', { name: /Cost Price/i })).toBeTruthy()

    const nameCard = screen.getByTestId('clarification-card-Cust Name')
    expect(within(nameCard).getByRole('button', { name: /Customer/i })).toBeTruthy()
    expect(within(nameCard).getByRole('button', { name: /Item/i })).toBeTruthy()
  })

  it('renders only pre-masked sample values and preserves PII safeguards', () => {
    render(
      <GroupedClarificationDialog
        open
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Customer', 'Item']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const nameCard = screen.getByTestId('clarification-card-Cust Name')
    // Pre-masked value [redacted] is shown; raw sensitive names are never exposed
    expect(within(nameCard).getAllByText('[redacted]').length).toBeGreaterThan(0)

    const rateCard = screen.getByTestId('clarification-card-Rate')
    expect(within(rateCard).getByText('₹ 250.00')).toBeTruthy()
  })

  it('treats "Something else" as a clarification note and requires explicit role selection', () => {
    const onApply = vi.fn()
    render(
      <GroupedClarificationDialog
        open
        columns={[SAMPLE_AMBIGUOUS_COLUMNS[0]]}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Line Total', 'Tax']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={onApply}
        onSkip={vi.fn()}
      />
    )

    // Expand "Something else"
    const toggleBtn = screen.getByRole('button', { name: /Something else/i })
    fireEvent.click(toggleBtn)

    // Type a note
    const noteInput = screen.getByPlaceholderText(/e\.g\. Delivery surcharge/i)
    fireEvent.change(noteInput, { target: { value: 'Custom wholesale markup fee' } })

    // Explicitly select a valid canonical role from the dropdown
    const roleSelect = screen.getByLabelText(/Select canonical role for Rate/i)
    fireEvent.change(roleSelect, { target: { value: 'Cost Price' } })

    // Apply mappings
    fireEvent.click(screen.getByRole('button', { name: /Apply mappings/i }))

    expect(onApply).toHaveBeenCalledWith(
      { Rate: 'Cost Price' },
      { Rate: 'Custom wholesale markup fee' }
    )
  })

  it('calls onSkip without modifying or resetting mappings when dismissed', () => {
    const onSkip = vi.fn()
    const onApply = vi.fn()
    render(
      <GroupedClarificationDialog
        open
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price']}
        fieldHelp={{}}
        currentMapping={{ Rate: 'Selling Price' }}
        onApply={onApply}
        onSkip={onSkip}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /Skip for now/i }))
    expect(onSkip).toHaveBeenCalled()
    expect(onApply).not.toHaveBeenCalled()
  })

  it('calls onSkip when Escape key is pressed', () => {
    const onSkip = vi.fn()
    render(
      <GroupedClarificationDialog
        open
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={onSkip}
      />
    )

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' })
    expect(onSkip).toHaveBeenCalled()
  })
})

const PREVIEW_WITH_AMBIGUITY = {
    file_id: 'f_mod22',
    filename: 'test_invoice.csv',
    row_count: 5,
    required_fields: ['Date'],
    optional_fields: ['Line Total', 'Quantity', 'Selling Price', 'Cost Price', 'Customer', 'Item'],
    field_help: {},
    sample_rows: [
      {
        'Bill Date': '2026-01-01',
        'Net Amt': '500.00',
        Rate: '250.00',
      },
    ],
    ai_enabled: false,
    pipeline_timings: { tier1_ms: 10, evidence_ms: 5, tier2_ms: 0, total_ms: 15 },
    detected_columns: [
      {
        raw_column: 'Bill Date',
        suggested_field: 'Date',
        confidence: 'exact',
        confidence_score: 1.0,
        confidence_band: 'high',
        source: 'local',
        needs_review: false,
      },
      {
        raw_column: 'Net Amt',
        suggested_field: 'Line Total',
        confidence: 'exact',
        confidence_score: 1.0,
        confidence_band: 'high',
        source: 'local',
        needs_review: false,
      },
      {
        raw_column: 'Rate',
        suggested_field: null,
        confidence: 'fuzzy',
        confidence_score: 0.4,
        confidence_band: 'low',
        source: 'fallback',
        needs_review: true,
        evidence_candidates: ['Selling Price', 'Cost Price'],
        evidence_reason: 'Could be Selling Price or Cost Price.',
        evidence_facts: ['Values look numeric.'],
      },
    ],
  }

describe('ColumnMappingScreen integration with clarification dialog (Module 2.2)', () => {
  it('renders a clarification banner when ambiguous columns exist', () => {
    render(<ColumnMappingScreen preview={PREVIEW_WITH_AMBIGUITY} onConfirm={vi.fn()} onCancel={vi.fn()} />)

    const banner = screen.getByTestId('clarification-banner')
    expect(banner).toBeTruthy()
    expect(within(banner).getByText(/1 column\(s\) need clarification/i)).toBeTruthy()
    expect(within(banner).getByRole('button', { name: /Clarify columns \(1\)/i })).toBeTruthy()
  })

  it('skipping clarification never blocks confirmation when Phase 1 requirements are met', () => {
    // PREVIEW_WITH_AMBIGUITY already maps Bill Date -> Date, Net Amt -> Line Total (Path A satisfied!)
    render(<ColumnMappingScreen preview={PREVIEW_WITH_AMBIGUITY} onConfirm={vi.fn()} onCancel={vi.fn()} />)

    // Confirm button must be enabled
    const confirmBtn = screen.getByRole('button', { name: /Confirm & analyse/i })
    expect(confirmBtn.disabled).toBe(false)
  })

  it('applying dialog selections overrides automated suggestions and shows "User choice" badge', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    // Dialog is open
    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Select candidate 'Selling Price' for 'Rate'
    const candidateBtn = within(dialog).getByRole('button', { name: /Selling Price/i })
    fireEvent.click(candidateBtn)

    // Click Apply mappings
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))

    // Dialog closes
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // The table row for 'Rate' now displays "User choice"
    expect(screen.getByText('User choice')).toBeTruthy()
    expect(screen.getByText('from your selection')).toBeTruthy()

    // The dropdown for Rate is updated to Selling Price
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    expect(rateSelect.value).toBe('Selling Price')
  })

  it('manual dropdown changes also display "User choice" consistently', () => {
    render(<ColumnMappingScreen preview={PREVIEW_WITH_AMBIGUITY} onConfirm={vi.fn()} onCancel={vi.fn()} />)

    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    fireEvent.change(rateSelect, { target: { value: 'Cost Price' } })

    // Displays User choice
    expect(screen.getByText('User choice')).toBeTruthy()
    expect(screen.getByText('from your selection')).toBeTruthy()
  })

  it('supports dismissing, reopening, and ignoring a column while preserving existing mappings', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    // Initially open
    let dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Dismiss dialog via "Skip for now"
    fireEvent.click(within(dialog).getByRole('button', { name: /Skip for now/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Table preserves existing mappings
    const dateSelect = screen.getByLabelText('Map column Bill Date to a field')
    const netAmtSelect = screen.getByLabelText('Map column Net Amt to a field')
    expect(dateSelect.value).toBe('Date')
    expect(netAmtSelect.value).toBe('Line Total')

    // Reopen dialog using banner button
    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    fireEvent.click(clarifyBtn)
    dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Click "Ignore this column" for Rate
    const ignoreBtn = within(dialog).getByRole('button', { name: /Ignore this column/i })
    fireEvent.click(ignoreBtn)

    // Apply mappings
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Existing mappings are preserved and Rate is ignored ("") without unintended canonical assignment
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    expect(rateSelect.value).toBe('')
    expect(dateSelect.value).toBe('Date')
    expect(netAmtSelect.value).toBe('Line Total')
  })

  it('banner count and button label accurately distinguish unresolved columns from all ambiguous columns', () => {
    const MULTI_AMBIGUOUS_PREVIEW = {
      ...PREVIEW_WITH_AMBIGUITY,
      detected_columns: [
        ...PREVIEW_WITH_AMBIGUITY.detected_columns,
        {
          raw_column: 'Cust Name',
          suggested_field: null,
          confidence: 'fuzzy',
          confidence_score: 0.45,
          confidence_band: 'low',
          source: 'fallback',
          needs_review: true,
          evidence_candidates: ['Customer', 'Item'],
          evidence_reason: 'Could be Customer or Item.',
        },
      ],
    }

    render(
      <ColumnMappingScreen
        preview={MULTI_AMBIGUOUS_PREVIEW}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const banner = screen.getByTestId('clarification-banner')
    // Both are unresolved initially
    expect(within(banner).getByText('2 column(s) need clarification based on data evidence.')).toBeTruthy()
    expect(within(banner).getByRole('button', { name: 'Clarify columns (2)' })).toBeTruthy()

    // Review one column by changing its table dropdown
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    fireEvent.change(rateSelect, { target: { value: 'Selling Price' } })

    // Banner count updates to 1 unresolved, while button still reflects all 2 ambiguous columns
    expect(within(banner).getByText('1 column(s) need clarification based on data evidence.')).toBeTruthy()
    expect(within(banner).getByRole('button', { name: 'Clarify columns (2)' })).toBeTruthy()

    // Review second column
    const custSelect = screen.getByLabelText('Map column Cust Name to a field')
    fireEvent.change(custSelect, { target: { value: 'Customer' } })

    // All are reviewed, but button still allows re-clarifying all 2
    expect(within(banner).getByText('All ambiguous columns have been reviewed.')).toBeTruthy()
    expect(within(banner).getByRole('button', { name: 'Clarify columns (2)' })).toBeTruthy()
  })
})

describe('Upload to ColumnMappingScreen call path (Module 2.2)', () => {
  beforeEach(() => {
    useSalesStore.setState({
      fetchAiCapabilities: vi.fn(),
      mappingPreview: null,
      isLoading: false,
      error: null,
      aiConsentAnswer: true,
      aiConsent: true,
      aiAvailable: false,
      pipelineTimings: null,
    })
  })

  it('passes initialOpenClarification as true when ambiguous columns exist, auto-opening the dialog', () => {
    useSalesStore.setState({ mappingPreview: PREVIEW_WITH_AMBIGUITY })

    render(
      <HelmetProvider>
        <MemoryRouter>
          <Upload />
        </MemoryRouter>
      </HelmetProvider>
    )

    // Dialog is open automatically on initial render of Upload with ambiguous preview
    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()
    expect(screen.getByText(/Clarify ambiguous columns/i)).toBeTruthy()

    // User can dismiss it without losing anything
    fireEvent.click(within(dialog).getByRole('button', { name: /Skip for now/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Confirm button is ready and enabled (Path A met: Date + Line Total)
    const confirmBtn = screen.getByRole('button', { name: /Confirm & analyse/i })
    expect(confirmBtn.disabled).toBe(false)
  })

  it('passes initialOpenClarification as false when no ambiguous columns exist, keeping dialog closed', () => {
    const CLEAN_PREVIEW = {
      ...PREVIEW_WITH_AMBIGUITY,
      detected_columns: [
        {
          raw_column: 'Bill Date',
          suggested_field: 'Date',
          confidence: 'exact',
          confidence_score: 1.0,
          confidence_band: 'high',
          source: 'local',
          needs_review: false,
          evidence_candidates: [],
        },
        {
          raw_column: 'Net Amt',
          suggested_field: 'Line Total',
          confidence: 'exact',
          confidence_score: 1.0,
          confidence_band: 'high',
          source: 'local',
          needs_review: false,
          evidence_candidates: [],
        },
      ],
    }

    useSalesStore.setState({ mappingPreview: CLEAN_PREVIEW })

    render(
      <HelmetProvider>
        <MemoryRouter>
          <Upload />
        </MemoryRouter>
      </HelmetProvider>
    )

    // No dialog open, no clarification banner shown
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()
    expect(screen.queryByTestId('clarification-banner')).toBeNull()
  })
})

describe('State management & synchronization (Module 2.2)', () => {
  const MULTI_AMBIGUOUS_PREVIEW = {
    ...PREVIEW_WITH_AMBIGUITY,
    detected_columns: [
      ...PREVIEW_WITH_AMBIGUITY.detected_columns,
      {
        raw_column: 'Cust Name',
        suggested_field: null,
        confidence: 'fuzzy',
        confidence_score: 0.45,
        confidence_band: 'low',
        source: 'fallback',
        needs_review: true,
        evidence_candidates: ['Customer', 'Item'],
        evidence_reason: 'Could be Customer or Item.',
      },
    ],
  }

  it('changes a mapping in the table, reopens the dialog, and confirms the latest selection is shown', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    // Change Rate to 'Cost Price' in the table dropdown
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    fireEvent.change(rateSelect, { target: { value: 'Cost Price' } })
    expect(rateSelect.value).toBe('Cost Price')

    // Reopen the dialog
    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    fireEvent.click(clarifyBtn)

    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Confirm that the dialog synchronized with currentMapping and shows 'Selected: Cost Price'
    const rateCard = screen.getByTestId('clarification-card-Rate')
    expect(within(rateCard).getByText('Selected: Cost Price')).toBeTruthy()
  })

  it('preserves deliberate in-dialog edits while dialog remains open without unexpected resets', () => {
    const { rerender } = render(
      <GroupedClarificationDialog
        open={true}
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Customer', 'Item']}
        fieldHelp={{}}
        currentMapping={{ Rate: 'Cost Price', 'Cust Name': 'Item' }}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const rateCard = screen.getByTestId('clarification-card-Rate')
    expect(within(rateCard).getByText('Selected: Cost Price')).toBeTruthy()

    // Deliberately choose 'Selling Price' inside the open dialog
    const sellingPriceBtn = within(rateCard).getByRole('button', { name: /Selling Price/i })
    fireEvent.click(sellingPriceBtn)
    expect(within(rateCard).getByText('Selected: Selling Price')).toBeTruthy()

    // Deliberately expand Something Else and enter a note
    const toggleBtn = within(rateCard).getByRole('button', { name: /Something else/i })
    fireEvent.click(toggleBtn)
    const noteInput = within(rateCard).getByPlaceholderText(/e\.g\. Delivery surcharge/i)
    fireEvent.change(noteInput, { target: { value: 'Vendor base rate' } })

    // Rerender dialog while open (e.g. parent re-render or prop change)
    rerender(
      <GroupedClarificationDialog
        open={true}
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'MRP', 'Cost Price', 'Customer', 'Item']}
        fieldHelp={{}}
        currentMapping={{ Rate: 'Cost Price', 'Cust Name': 'Item' }}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    // Verify deliberate in-dialog edits were NOT reset
    expect(within(rateCard).getByText('Selected: Selling Price')).toBeTruthy()
    expect(within(rateCard).getByDisplayValue('Vendor base rate')).toBeTruthy()
  })

  it('applies after reopening without overwriting a newer manual choice', () => {
    render(
      <ColumnMappingScreen
        preview={MULTI_AMBIGUOUS_PREVIEW}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    // Dialog is initially open
    let dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // User dismisses dialog via "Skip for now"
    fireEvent.click(within(dialog).getByRole('button', { name: /Skip for now/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // User manually sets Cust Name to 'Customer' in the table
    const custSelect = screen.getByLabelText('Map column Cust Name to a field')
    fireEvent.change(custSelect, { target: { value: 'Customer' } })
    expect(custSelect.value).toBe('Customer')

    // Re-open the dialog
    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(2\)/i })
    fireEvent.click(clarifyBtn)
    dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Verify Cust Name in dialog reflects the latest manual table selection 'Customer'
    const custCard = screen.getByTestId('clarification-card-Cust Name')
    expect(within(custCard).getByText('Selected: Customer')).toBeTruthy()

    // In the dialog, user only changes Rate to 'Selling Price' and leaves Cust Name untouched
    const rateCard = screen.getByTestId('clarification-card-Rate')
    const sellingPriceBtn = within(rateCard).getByRole('button', { name: /Selling Price/i })
    fireEvent.click(sellingPriceBtn)

    // Apply mappings
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Confirm Rate was updated to 'Selling Price'
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    expect(rateSelect.value).toBe('Selling Price')

    // Confirm Cust Name was NOT overwritten by stale dialog state and remains 'Customer'
    expect(custSelect.value).toBe('Customer')
  })

  it('applies one changed column without falsely marking every untouched column as a user choice', () => {
    render(
      <ColumnMappingScreen
        preview={MULTI_AMBIGUOUS_PREVIEW}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Only touch Rate in the dialog
    const rateCard = screen.getByTestId('clarification-card-Rate')
    const candidateBtn = within(rateCard).getByRole('button', { name: /Selling Price/i })
    fireEvent.click(candidateBtn)

    // Cust Name is NOT touched in the dialog
    // Apply mappings
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Rate was touched, so it receives "User choice"
    const rows = screen.getAllByRole('row')
    const rateRow = rows.find((r) => r.textContent.includes('Rate'))
    expect(within(rateRow).getByText('User choice')).toBeTruthy()

    // Cust Name was untouched, so it does NOT receive "User choice"
    const custRow = rows.find((r) => r.textContent.includes('Cust Name'))
    expect(within(custRow).queryByText('User choice')).toBeNull()

    // Untouched auto-detected columns do NOT receive "User choice"
    const dateRow = rows.find((r) => r.textContent.includes('Bill Date'))
    expect(within(dateRow).queryByText('User choice')).toBeNull()
    const netAmtRow = rows.find((r) => r.textContent.includes('Net Amt'))
    expect(within(netAmtRow).queryByText('User choice')).toBeNull()
  })

  it('clicking Apply mappings without changing any column does NOT mark untouched automatic suggestions as user choices', () => {
    render(
      <ColumnMappingScreen
        preview={MULTI_AMBIGUOUS_PREVIEW}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Do NOT touch any column, simply click "Apply mappings"
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Verify NONE of the rows were marked as "User choice"
    const rows = screen.getAllByRole('row')
    for (const row of rows) {
      expect(within(row).queryByText('User choice')).toBeNull()
    }
  })

  it('explicitly ignores a column and verifies it remains unmapped and marked as reviewed', () => {
    const onConfirm = vi.fn()
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        initialOpenClarification={true}
      />
    )

    const dialog = screen.getByTestId('grouped-clarification-dialog')

    // Click "Ignore this column" for Rate
    const ignoreBtn = within(dialog).getByRole('button', { name: /Ignore this column/i })
    fireEvent.click(ignoreBtn)

    // Apply mappings
    fireEvent.click(within(dialog).getByRole('button', { name: /Apply mappings/i }))
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Rate is unmapped in the table
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    expect(rateSelect.value).toBe('')

    // Rate was explicitly ignored by user, so it is marked as user choice and reviewed
    const rows = screen.getAllByRole('row')
    const rateRow = rows.find((r) => r.textContent.includes('Rate'))
    expect(within(rateRow).getByText('User choice')).toBeTruthy()

    // Clarification banner reflects that all ambiguous columns have been reviewed
    const banner = screen.getByTestId('clarification-banner')
    expect(within(banner).getByText('All ambiguous columns have been reviewed.')).toBeTruthy()

    // Confirm that confirmMapping can be submitted and sends Rate as empty/ignored
    const confirmBtn = screen.getByRole('button', { name: /Confirm & analyse/i })
    fireEvent.click(confirmBtn)
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        'Bill Date': 'Date',
        'Net Amt': 'Line Total',
        Rate: '',
      }),
      expect.anything(),
      expect.anything(),
    )
  })

  it('explicitly ignoring a column in table displays it as Unmapped upon reopening dialog', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    // User explicitly sets Rate to empty in the table dropdown
    const rateSelect = screen.getByLabelText('Map column Rate to a field')
    fireEvent.change(rateSelect, { target: { value: '' } })
    expect(rateSelect.value).toBe('')

    // Reopen dialog
    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    fireEvent.click(clarifyBtn)
    const dialog = screen.getByTestId('grouped-clarification-dialog')

    // Confirm Rate is shown as Unmapped in dialog
    const rateCard = screen.getByTestId('clarification-card-Rate')
    expect(within(rateCard).getByText('Unmapped')).toBeTruthy()
  })
})

describe('Focus containment and focus restoration (Module 2.2 accessibility)', () => {
  it('moves initial focus to the first focusable element inside the dialog on mount', () => {
    render(
      <GroupedClarificationDialog
        open={true}
        columns={SAMPLE_AMBIGUOUS_COLUMNS}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'Cost Price']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const closeBtn = screen.getByRole('button', { name: /Close dialog without saving/i })
    expect(document.activeElement).toBe(closeBtn)
  })

  it('wraps focus from last focusable element to first focusable element on Tab key', () => {
    render(
      <GroupedClarificationDialog
        open={true}
        columns={[SAMPLE_AMBIGUOUS_COLUMNS[0]]}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'Cost Price']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const closeBtn = screen.getByRole('button', { name: /Close dialog without saving/i })
    const applyBtn = screen.getByRole('button', { name: /Apply mappings/i })

    // Focus last element
    applyBtn.focus()
    expect(document.activeElement).toBe(applyBtn)

    // Press Tab
    fireEvent.keyDown(window, { key: 'Tab', code: 'Tab' })

    // Focus wraps to the first focusable element
    expect(document.activeElement).toBe(closeBtn)
  })

  it('wraps focus from first focusable element to last focusable element on Shift+Tab key', () => {
    render(
      <GroupedClarificationDialog
        open={true}
        columns={[SAMPLE_AMBIGUOUS_COLUMNS[0]]}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price', 'Cost Price']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const closeBtn = screen.getByRole('button', { name: /Close dialog without saving/i })
    const applyBtn = screen.getByRole('button', { name: /Apply mappings/i })

    // Focus first element
    closeBtn.focus()
    expect(document.activeElement).toBe(closeBtn)

    // Press Shift+Tab
    fireEvent.keyDown(window, { key: 'Tab', code: 'Tab', shiftKey: true })

    // Focus wraps to the last focusable element
    expect(document.activeElement).toBe(applyBtn)
  })

  it('redirects focus back into dialog if focus escapes to an external element', () => {
    const outsideBtn = document.createElement('button')
    outsideBtn.textContent = 'Outside Button'
    document.body.appendChild(outsideBtn)

    render(
      <GroupedClarificationDialog
        open={true}
        columns={[SAMPLE_AMBIGUOUS_COLUMNS[0]]}
        sampleRows={SAMPLE_MASKED_ROWS}
        allFields={['Date', 'Selling Price']}
        fieldHelp={{}}
        currentMapping={{}}
        onApply={vi.fn()}
        onSkip={vi.fn()}
      />
    )

    const closeBtn = screen.getByRole('button', { name: /Close dialog without saving/i })
    expect(document.activeElement).toBe(closeBtn)

    // Attempt to focus outside element
    outsideBtn.focus()
    fireEvent.focusIn(outsideBtn)

    // Focus is contained and pulled back into dialog
    expect(document.activeElement).toBe(closeBtn)

    document.body.removeChild(outsideBtn)
  })

  it('restores focus to the opener element when dialog closes via Escape key', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    clarifyBtn.focus()
    expect(document.activeElement).toBe(clarifyBtn)

    // Open dialog by clicking opener
    fireEvent.click(clarifyBtn)
    expect(screen.getByTestId('grouped-clarification-dialog')).toBeTruthy()

    // Dismiss with Escape key
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' })

    // Dialog is closed
    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()

    // Focus is restored to the opener button
    expect(document.activeElement).toBe(clarifyBtn)
  })

  it('restores focus to the opener element when dialog closes via the close button (✕)', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    clarifyBtn.focus()

    fireEvent.click(clarifyBtn)
    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    const closeBtn = screen.getByRole('button', { name: /Close dialog without saving/i })
    fireEvent.click(closeBtn)

    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()
    expect(document.activeElement).toBe(clarifyBtn)
  })

  it('restores focus to the opener element when dialog closes via backdrop click', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    clarifyBtn.focus()

    fireEvent.click(clarifyBtn)
    const dialog = screen.getByTestId('grouped-clarification-dialog')
    expect(dialog).toBeTruthy()

    // Click backdrop
    const backdrop = dialog.querySelector('[aria-hidden="true"]')
    expect(backdrop).toBeTruthy()
    fireEvent.click(backdrop)

    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()
    expect(document.activeElement).toBe(clarifyBtn)
  })

  it('restores focus to the opener element when dialog closes via Skip for now button', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const clarifyBtn = screen.getByRole('button', { name: /Clarify columns \(1\)/i })
    clarifyBtn.focus()

    fireEvent.click(clarifyBtn)
    expect(screen.getByTestId('grouped-clarification-dialog')).toBeTruthy()

    const skipBtn = screen.getByRole('button', { name: /Skip for now/i })
    fireEvent.click(skipBtn)

    expect(screen.queryByTestId('grouped-clarification-dialog')).toBeNull()
    expect(document.activeElement).toBe(clarifyBtn)
  })
})

describe('Module 2.3 Safe Mapping Memory UI & Opt-In Behaviour', () => {
  const PREVIEW_WITH_MEMORY = {
    ...PREVIEW_WITH_AMBIGUITY,
    detected_columns: [
      {
        raw_column: 'Invoice Date',
        suggested_field: 'Date',
        confidence: 'exact',
        confidence_score: 1.0,
        confidence_band: 'high',
        route: 'local',
        source: 'local',
        semantic_label: 'date',
        reason: 'Matches invoice date',
        needs_review: false,
      },
      {
        raw_column: 'Rate',
        suggested_field: 'Selling Price',
        confidence: 'exact',
        confidence_score: 0.95,
        confidence_band: 'high',
        route: 'local',
        source: 'memory',
        semantic_label: 'unit_price',
        reason: 'Recalled from saved mapping memory for this template.',
        needs_review: false,
      },
    ],
  }

  it('renders the remember-mapping checkbox unchecked by default (opt-in)', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const checkbox = screen.getByTestId('remember-mapping-checkbox')
    expect(checkbox).toBeTruthy()
    expect(checkbox.checked).toBe(false)
  })

  it('submits with rememberMapping=false when user does not check the box', () => {
    const onConfirm = vi.fn()
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    const confirmBtn = screen.getByRole('button', { name: /Confirm & analyse/i })
    fireEvent.click(confirmBtn)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    const [mapping, userSelected, rememberMapping] = onConfirm.mock.calls[0]
    expect(rememberMapping).toBe(false)
  })

  it('submits with rememberMapping=true and explicitly selected columns when opted in', () => {
    const onConfirm = vi.fn()
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_AMBIGUITY}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    // User changes a column
    const select = screen.getByLabelText(/Map column Rate to a field/i)
    fireEvent.change(select, { target: { value: 'Cost Price' } })

    // User opts in
    const checkbox = screen.getByTestId('remember-mapping-checkbox')
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)

    const confirmBtn = screen.getByRole('button', { name: /Confirm & analyse/i })
    fireEvent.click(confirmBtn)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    const [mapping, userSelected, rememberMapping] = onConfirm.mock.calls[0]
    expect(rememberMapping).toBe(true)
    expect(userSelected).toContain('Rate')
    expect(mapping['Rate']).toBe('Cost Price')
  })

  it('renders Memory badge and reason for columns resolved by safe mapping memory', () => {
    render(
      <ColumnMappingScreen
        preview={PREVIEW_WITH_MEMORY}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        initialOpenClarification={false}
      />
    )

    expect(screen.getByText('Memory')).toBeTruthy()
    expect(screen.getByText(/Recalled from saved mapping memory for this template/i)).toBeTruthy()
  })
})




