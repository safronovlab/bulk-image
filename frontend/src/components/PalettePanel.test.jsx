/**
 * Failing tests for frontend/src/components/PalettePanel.jsx.
 *
 * Covers PalettePanel_spec.md §5 + every [SRE_MARKER]. Uses
 * @testing-library/react + @testing-library/user-event.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PalettePanel from './PalettePanel';

vi.mock('../api', () => ({
  api: {
    createPalette: vi.fn(async ({ label, entries }) => ({
      palette_id: '01H8XGJWBWBAQ4ZQH8K1MABCDE',
      label,
      entries,
      created_at: '2026-05-07T00:00:00Z',
    })),
  },
}));

const chicago = {
  palette_id: '01H8XGJWBWBAQ4ZQH8K1MCHCAGO',
  label: 'chicago',
  entries: [
    { source_hex: null, target_hex: '#FF0018' },
    { source_hex: null, target_hex: '#FFFFFF' },
    { source_hex: null, target_hex: '#000000' },
  ],
  created_at: '2026-05-07T00:00:00Z',
};

describe('PalettePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders_one_default_entry_when_initial_palette_null', () => {
    render(<PalettePanel onPaletteCreated={vi.fn()} initialPalette={null} />);
    const inputs = screen.getAllByRole('textbox');
    // At least one entry input present
    expect(inputs.length).toBeGreaterThanOrEqual(1);
  });

  it('hydrates_from_initial_palette', () => {
    render(<PalettePanel onPaletteCreated={vi.fn()} initialPalette={chicago} />);
    expect(screen.getByDisplayValue('#FF0018')).toBeInTheDocument();
    expect(screen.getByDisplayValue('#FFFFFF')).toBeInTheDocument();
    expect(screen.getByDisplayValue('#000000')).toBeInTheDocument();
  });

  it('add_color_button_disabled_at_five_entries', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const addBtn = screen.getByRole('button', { name: /add color/i });
    for (let i = 0; i < 4; i++) {
      await user.click(addBtn);
    }
    expect(addBtn).toBeDisabled();
  });

  it('remove_color_button_disabled_at_one_entry', () => {
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const remove = screen.queryByRole('button', { name: /remove/i });
    if (remove) {
      expect(remove).toBeDisabled();
    }
  });

  it('rejects_invalid_hex_shows_field_error', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const input = screen.getAllByRole('textbox')[0];
    await user.clear(input);
    await user.type(input, '#GGGGGG');
    await waitFor(() => {
      expect(screen.getByText(/#RRGGBB/i)).toBeInTheDocument();
    });
  });

  it('rejects_invalid_label_charset', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const labelInput = screen.getByLabelText(/label/i);
    await user.clear(labelInput);
    await user.type(labelInput, '../etc');
    await waitFor(() => {
      expect(screen.getByText(/letters, numbers/i)).toBeInTheDocument();
    });
  });

  it('calls_on_palette_change_on_each_edit', async () => {
    const onPaletteChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PalettePanel onPaletteCreated={vi.fn()} onPaletteChange={onPaletteChange} />,
    );
    const labelInput = screen.getByLabelText(/label/i);
    await user.type(labelInput, 'a');
    expect(onPaletteChange).toHaveBeenCalled();
  });

  it('calls_on_palette_created_on_success', async () => {
    const user = userEvent.setup();
    const onPaletteCreated = vi.fn();
    render(<PalettePanel onPaletteCreated={onPaletteCreated} initialPalette={chicago} />);
    const submit = screen.getByRole('button', { name: /save palette/i });
    await user.click(submit);
    await waitFor(() => {
      expect(onPaletteCreated).toHaveBeenCalled();
    });
  });

  it('disables_submit_during_pending_request', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} initialPalette={chicago} />);
    const submit = screen.getByRole('button', { name: /save palette/i });
    await user.click(submit);
    expect(submit).toBeDisabled();
  });

  it('disables_all_when_disabled_prop_true', () => {
    render(<PalettePanel onPaletteCreated={vi.fn()} disabled={true} initialPalette={chicago} />);
    const inputs = screen.getAllByRole('textbox');
    for (const inp of inputs) {
      expect(inp).toBeDisabled();
    }
  });

  it('pasting_comma_separated_hexes_creates_multiple_rows', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const input = screen.getAllByRole('textbox')[0];
    await user.click(input);
    await user.paste('#FF0018, #FFFFFF, #000000');
    expect(screen.getByDisplayValue('#FF0018')).toBeInTheDocument();
    expect(screen.getByDisplayValue('#FFFFFF')).toBeInTheDocument();
    expect(screen.getByDisplayValue('#000000')).toBeInTheDocument();
  });

  it('submit_blocks_duplicate_clicks', async () => {
    const user = userEvent.setup();
    const { api } = await import('../api');
    render(<PalettePanel onPaletteCreated={vi.fn()} initialPalette={chicago} />);
    const submit = screen.getByRole('button', { name: /save palette/i });
    await user.dblClick(submit);
    // Only one POST per the spec
    expect(api.createPalette).toHaveBeenCalledTimes(1);
  });

  // SRE_MARKER risk=input (line 11)
  it('parses_pasted_rgba_hex_strips_alpha', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const input = screen.getAllByRole('textbox')[0];
    await user.click(input);
    await user.paste('#FF0018FF');
    // Either the alpha is stripped (result #FF0018) or a warning shows.
    expect(
      screen.queryByDisplayValue('#FF0018') ||
        screen.queryByText(/alpha/i),
    ).toBeTruthy();
  });

  // SRE_MARKER risk=idempotency (line 12)
  it('test_submit_truly_single_dispatch_under_event_loop_thrash', async () => {
    const user = userEvent.setup();
    const { api } = await import('../api');
    render(<PalettePanel onPaletteCreated={vi.fn()} initialPalette={chicago} />);
    const submit = screen.getByRole('button', { name: /save palette/i });
    // Hammer the button rapidly via fireEvent (synchronous) and userEvent
    fireEvent.click(submit);
    fireEvent.click(submit);
    fireEvent.click(submit);
    await user.click(submit);
    // Strict: still exactly one POST
    expect(api.createPalette).toHaveBeenCalledTimes(1);
  });

  // SRE_MARKER risk=observability (line 127)
  it('test_on_palette_change_debounced', async () => {
    const onPaletteChange = vi.fn();
    const user = userEvent.setup();
    render(
      <PalettePanel onPaletteCreated={vi.fn()} onPaletteChange={onPaletteChange} />,
    );
    const labelInput = screen.getByLabelText(/label/i);
    // Type 5 chars rapidly
    await user.type(labelInput, 'abcde');
    // Debounced at 250ms — there should be < 5 calls in total.
    expect(onPaletteChange.mock.calls.length).toBeLessThan(5);
  });

  // SRE_MARKER risk=security (line 128)
  it('test_label_rejects_zero_width_chars', async () => {
    const user = userEvent.setup();
    render(<PalettePanel onPaletteCreated={vi.fn()} />);
    const labelInput = screen.getByLabelText(/label/i);
    await user.clear(labelInput);
    await user.type(labelInput, 'chic​ago');
    // Either rejected at input or normalised away
    await waitFor(() => {
      const value = labelInput.value;
      expect(value).not.toContain('​');
    });
  });
});
