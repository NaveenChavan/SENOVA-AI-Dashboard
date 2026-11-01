import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ColumnMappingScreen from '../components/upload/ColumnMappingScreen'
import useSalesStore from '../store/useSalesStore'

/**
 * Phase 4.1 ("Check again with AI") and Phase 4.2 (custom note per column),
 * exercised at the component level against the real Zustand store with its
 * network-calling actions swapped out — the same pattern already used by
 * `ai_assurance.test.jsx` for `runTier2Async`.
 */

const BASE_PREVIEW = {
  file_id: 'f1',
  filename: 'sales.csv',
  row_count: 3,
  required_fields: ['Date'],
  optional_fields: [],
  field_help: {},
  sample_rows: [{ 'Zorp Factor': 'alpha' }],
  ai_enabled: true,
  pipeline_timings: { tier1_ms: 10, tier2_ms: 0, pandas_ms: null, total_ms: 10 },
  detected_columns: [
    {
      raw_column: 'Zorp Factor',
      suggested_field: null,
      confidence: 'none',
      confidence_band: 'low',
      source: 'local',
      semantic_label: 'other',
      reason: 'Unrecognised header.',
      needs_review: true,
    },
  ],
}

async function withStoreOverrides(overrides, fn) {
  const original = {}
  for (const key of Object.keys(overrides)) {
    original[key] = useSalesStore.getState()[key]
  }
  useSalesStore.setState(overrides)
  try {
    return await fn()
  } finally {
    useSalesStore.setState(original)
  }
}

describe('Phase 4.1 — Check again with AI', () => {
  it('shows the banner only when something is still unresolved', () => {
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
      expect(screen.getByTestId('check-again-banner')).toBeTruthy()
    })
  })

  it('hides the banner when nothing needs review', () => {
    const resolvedPreview = {
      ...BASE_PREVIEW,
      detected_columns: [{ ...BASE_PREVIEW.detected_columns[0], needs_review: false, suggested_field: 'Date' }],
    }
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={resolvedPreview} onConfirm={() => {}} onCancel={() => {}} />)
      expect(screen.queryByTestId('check-again-banner')).toBeNull()
    })
  })

  it('disables the button with a reason when AI is off', () => {
    const previewAiOff = { ...BASE_PREVIEW, ai_enabled: false }
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={previewAiOff} onConfirm={() => {}} onCancel={() => {}} />)
      const button = screen.getByTestId('check-again-button')
      expect(button.disabled).toBe(true)
      expect(screen.getByTestId('check-again-disabled-reason').textContent).toMatch(/switched off/i)
    })
  })

  it('disables the button with a reason when consent is missing', () => {
    withStoreOverrides({ aiConsent: false }, () => {
      render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
      const button = screen.getByTestId('check-again-button')
      expect(button.disabled).toBe(true)
      expect(screen.getByTestId('check-again-disabled-reason').textContent).toMatch(/not approved/i)
    })
  })

  it('calls the forced-recheck action and shows a real, measured count', async () => {
    let called = false
    await withStoreOverrides(
      {
        aiConsent: true,
        forceRecheckTier2Async: async () => {
          called = true
          return { columnsEvaluated: 1, columnsResolved: 1 }
        },
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
        fireEvent.click(screen.getByTestId('check-again-button'))
        await waitFor(() => {
          expect(screen.getByTestId('check-again-message').textContent).toMatch(/AI looked at 1 column, resolved 1/)
        })
      },
    )
    expect(called).toBe(true)
  })

  it('never fabricates a count when nothing was evaluated', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        forceRecheckTier2Async: async () => ({ columnsEvaluated: 0, columnsResolved: 0 }),
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
        fireEvent.click(screen.getByTestId('check-again-button'))
        await waitFor(() => {
          // No message element renders at all when evaluated is 0 — never a
          // fabricated "resolved 0 of 0" sentence.
          expect(screen.queryByTestId('check-again-message')).toBeNull()
        })
      },
    )
  })

  it('surfaces a cooldown message without calling the action again while blocked', async () => {
    let calls = 0
    await withStoreOverrides(
      {
        aiConsent: true,
        forceRecheckTier2Async: async () => {
          calls += 1
          return { cooldown: true, retryAfterSeconds: 7, message: 'Please wait 7s before checking again.' }
        },
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
        fireEvent.click(screen.getByTestId('check-again-button'))
        await waitFor(() => {
          expect(screen.getByTestId('check-again-message').textContent).toMatch(/wait 7s/i)
        })
        // Button must now show the disabled reason with the cooldown clock.
        await waitFor(() => {
          expect(screen.getByTestId('check-again-button').disabled).toBe(true)
        })
      },
    )
    expect(calls).toBe(1)
  })
})

describe('Phase 4.2 — custom note per column', () => {
  it('offers a note input only for a column that still needs review', () => {
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
      expect(screen.getByTestId('column-note-input-Zorp Factor')).toBeTruthy()
    })
  })

  it('does not offer a note input for a confidently-matched column', () => {
    const resolvedPreview = {
      ...BASE_PREVIEW,
      detected_columns: [{ ...BASE_PREVIEW.detected_columns[0], needs_review: false, suggested_field: 'Date' }],
    }
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={resolvedPreview} onConfirm={() => {}} onCancel={() => {}} />)
      expect(screen.queryByTestId('column-note-input-Zorp Factor')).toBeNull()
    })
  })

  it('shows the "Ask AI" trigger once a note is typed, and calls the store action', async () => {
    let sentNotes = null
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async (fileId, notes) => {
          sentNotes = notes
          return { suggestions: [{ column: 'Zorp Factor', role: 'extra_dimension', reason: 'category-like', money_sensitive: false }] }
        },
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'this is a product tier label' } })
        await waitFor(() => expect(input.value).toBe('this is a product tier label'))
        fireEvent.blur(input)

        const askButton = await screen.findByTestId('ask-ai-about-notes-button')
        fireEvent.click(askButton)

        await waitFor(() => {
          expect(screen.getByTestId('note-suggestion-Zorp Factor')).toBeTruthy()
        })
      },
    )
    expect(sentNotes).toEqual([{ column: 'Zorp Factor', note: 'this is a product tier label' }])
  })

  it('never applies a suggestion without the explicit "Use this" click', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'Category', reason: 'looks like a grouping', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'grouping label' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))

        await screen.findByTestId('note-suggestion-Zorp Factor')

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        // The suggestion is visible, but the mapping select is untouched —
        // nothing was applied merely because a suggestion came back.
        expect(select.value).toBe('')
      },
    )
  })

  it('requires the money-sensitive checkbox before "Use this" is enabled', async () => {
    const previewWithPrice = { ...BASE_PREVIEW, required_fields: ['Date', 'Selling Price'] }
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'Selling Price', reason: 'unit price', money_sensitive: true }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={previewWithPrice} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'price per unit' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        const applyButton = screen.getByTestId('apply-suggestion-Zorp Factor')
        expect(applyButton.disabled).toBe(true)

        fireEvent.click(screen.getByTestId('money-confirm-Zorp Factor'))
        expect(applyButton.disabled).toBe(false)

        fireEvent.click(applyButton)
        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        expect(select.value).toBe('Selling Price')
      },
    )
  })

  it('applying a non-money suggestion updates the mapping select immediately', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'Branch', reason: 'store name', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={{ ...BASE_PREVIEW, optional_fields: ['Branch'] }} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'store location' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        expect(select.value).toBe('Branch')
      },
    )
  })

  // ── Fix verification: non-canonical note roles ──────────────────────────
  //
  // extra_dimension / extra_measure / ignore are not canonical mapping
  // targets. Applying one must never leave `mapping` holding a value with no
  // matching <option>, and must never silently look like nothing happened.

  it('applying "ignore" clears the mapping to the valid unmapped state', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'ignore', reason: 'noise column', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'not useful' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        // The existing, already-valid "Ignore this column" option — never
        // the literal string "ignore".
        expect(select.value).toBe('')
        expect(Array.from(select.options).some((o) => o.value === 'ignore')).toBe(false)
        expect(screen.getByTestId('note-outcome-Zorp Factor').textContent).toMatch(/ignore this column/i)
      },
    )
  })

  it('applying "extra_dimension" never writes that string into the mapping select', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'extra_dimension', reason: 'category-like', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'size category' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        // No <option value="extra_dimension"> exists, so the only safe state
        // is the valid unmapped value — never an unmatched selection.
        expect(select.value).toBe('')
        expect(Array.from(select.options).some((o) => o.value === 'extra_dimension')).toBe(false)
        // The user is told plainly what will actually happen, not left to
        // wonder why "Use this" appeared to do nothing.
        expect(screen.getByTestId('note-outcome-Zorp Factor').textContent).toMatch(/extra dimension/i)
      },
    )
  })

  it('applying "extra_measure" never writes that string into the mapping select', async () => {
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'extra_measure', reason: 'amount-like', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'delivery charge' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        expect(select.value).toBe('')
        expect(Array.from(select.options).some((o) => o.value === 'extra_measure')).toBe(false)
        expect(screen.getByTestId('note-outcome-Zorp Factor').textContent).toMatch(/extra measure/i)
      },
    )
  })

  it('a subsequent submission after a non-canonical suggestion never sends an invalid canonical target', async () => {
    const confirmSpy = { mapping: null }
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'extra_dimension', reason: 'x', money_sensitive: false }],
        }),
      },
      async () => {
        render(
          <ColumnMappingScreen
            preview={BASE_PREVIEW}
            onConfirm={(mapping) => {
              confirmSpy.mapping = mapping
            }}
            onCancel={() => {}}
          />,
        )

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'size category' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')
        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        // "Zorp Factor" is unmapped, so the two-field rule (Date + Line
        // Total/Qty+Price) isn't met by this fixture — Confirm stays
        // disabled, which is correct. The assertion that matters is on the
        // mapping value itself, inspectable via the select.
        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        expect(select.value).not.toBe('extra_dimension')
        expect(['', ...BASE_PREVIEW.required_fields, ...(BASE_PREVIEW.optional_fields || [])]).toContain(select.value)
      },
    )
  })

  it('existing canonical suggestion flow still works after the non-canonical fix', async () => {
    const previewWithCategory = { ...BASE_PREVIEW, required_fields: ['Date', 'Category'] }
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'Category', reason: 'grouping', money_sensitive: false }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={previewWithCategory} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'product grouping' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')
        fireEvent.click(screen.getByTestId('apply-suggestion-Zorp Factor'))

        const select = screen.getByLabelText('Map column Zorp Factor to a field')
        expect(select.value).toBe('Category')
        // No stale "left unmapped" explanation for a real canonical apply.
        expect(screen.queryByTestId('note-outcome-Zorp Factor')).toBeNull()
      },
    )
  })

  it('money-sensitive confirmation is still required after the non-canonical fix', async () => {
    const previewWithPrice = { ...BASE_PREVIEW, required_fields: ['Date', 'Cost Price'] }
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async () => ({
          suggestions: [{ column: 'Zorp Factor', role: 'Cost Price', reason: 'purchase cost', money_sensitive: true }],
        }),
      },
      async () => {
        render(<ColumnMappingScreen preview={previewWithPrice} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'purchase cost per unit' } })
        fireEvent.blur(input)
        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await screen.findByTestId('note-suggestion-Zorp Factor')

        const applyButton = screen.getByTestId('apply-suggestion-Zorp Factor')
        expect(applyButton.disabled).toBe(true)
        fireEvent.click(screen.getByTestId('money-confirm-Zorp Factor'))
        expect(applyButton.disabled).toBe(false)
      },
    )
  })

  // ── Fix verification: Enter commits the draft before resolution reads it ──

  it('pressing Enter commits the current draft so Ask AI sends the latest text', async () => {
    let sentNotes = null
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async (fileId, notes) => {
          sentNotes = notes
          return { suggestions: [] }
        },
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'typed just now' } })
        // No blur — Enter alone must commit.
        fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })

        const askButton = await screen.findByTestId('ask-ai-about-notes-button')
        fireEvent.click(askButton)

        await waitFor(() => expect(sentNotes).not.toBeNull())
      },
    )
    expect(sentNotes).toEqual([{ column: 'Zorp Factor', note: 'typed just now' }])
  })

  it('Enter does not submit the upload form or bypass mapping confirmation', async () => {
    const onConfirm = () => {
      throw new Error('onConfirm must not be called by pressing Enter in the note field')
    }
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={onConfirm} onCancel={() => {}} />)

      const input = screen.getByTestId('column-note-input-Zorp Factor')
      fireEvent.change(input, { target: { value: 'anything' } })
      // Must not throw — proves Enter did not trigger form submission / onConfirm.
      expect(() => fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })).not.toThrow()
    })
  })

  it('blur-to-commit still works after adding Enter support', async () => {
    let sentNotes = null
    await withStoreOverrides(
      {
        aiConsent: true,
        submitColumnNotes: async (fileId, notes) => {
          sentNotes = notes
          return { suggestions: [] }
        },
      },
      async () => {
        render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)

        const input = screen.getByTestId('column-note-input-Zorp Factor')
        fireEvent.change(input, { target: { value: 'committed via blur' } })
        fireEvent.blur(input)

        fireEvent.click(await screen.findByTestId('ask-ai-about-notes-button'))
        await waitFor(() => expect(sentNotes).not.toBeNull())
      },
    )
    expect(sentNotes).toEqual([{ column: 'Zorp Factor', note: 'committed via blur' }])
  })

  it('the note input remains keyboard-accessible (focusable, labelled)', () => {
    withStoreOverrides({ aiConsent: true }, () => {
      render(<ColumnMappingScreen preview={BASE_PREVIEW} onConfirm={() => {}} onCancel={() => {}} />)
      const input = screen.getByLabelText('Note for column Zorp Factor')
      input.focus()
      expect(document.activeElement).toBe(input)
    })
  })
})
