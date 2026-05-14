/**
 * PalettePanel.jsx — palette setup panel (NEW in v2).
 *
 * Single responsibility: collect a palette (1..5 hex codes plus an optional
 * label) from the user and submit it via the API client. Visual companion of
 * BatchProcessTab and ColorStudioTab.
 *
 */

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Plus, X, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../api';
import { isValidHex, normalizeHex } from '../lib/colorMath';

const DEFAULT_TARGET = '#FF0018';
const LABEL_CHARSET = /^[A-Za-z0-9_-]*$/;
const LABEL_MAX = 32;
const HEX_PASTE_SPLIT = /[\s,]+/;
const ALLOWED_ASCII = /^[\x20-\x7E]*$/;

function makeEntry(target_hex = DEFAULT_TARGET) {
  return { source_hex: null, target_hex };
}

function sanitizeLabel(raw) {
  if (typeof raw !== 'string') return '';
  // Normalise unicode and strip non-ASCII (defends against zero-width chars).
  const normalized = raw.normalize ? raw.normalize('NFKD') : raw;
  return Array.from(normalized)
    .filter((ch) => ALLOWED_ASCII.test(ch))
    .join('');
}

function stripAlphaHex(text) {
  const t = (text || '').trim();
  const body = t.startsWith('#') ? t.slice(1) : t;
  if (body.length === 8 && /^[0-9A-Fa-f]{8}$/.test(body)) {
    return { value: `#${body.slice(0, 6).toUpperCase()}`, stripped: true };
  }
  return { value: t, stripped: false };
}

/**
 * @param {{
 *   initialPalette?: any,
 *   maxEntries?: number,
 *   minEntries?: number,
 *   onPaletteCreated: (palette: any) => void,
 *   onPaletteChange?: (draft: any) => void,
 *   disabled?: boolean,
 *   className?: string,
 * }} props
 */
export default function PalettePanel({
  initialPalette = null,
  maxEntries = 5,
  minEntries = 1,
  onPaletteCreated,
  onPaletteChange,
  disabled = false,
  className = '',
}) {
  const [label, setLabel] = useState(initialPalette?.label || '');
  const [entries, setEntries] = useState(
    initialPalette?.entries?.length
      ? initialPalette.entries.map((e) => ({
          source_hex: e.source_hex ?? null,
          target_hex: e.target_hex,
        }))
      : [makeEntry()],
  );
  const [labelError, setLabelError] = useState(null);
  const [hexErrors, setHexErrors] = useState({}); // index -> message
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [didSubmitOnce, setDidSubmitOnce] = useState(false);

  // Synchronous lock against double-submission.
  const submittingRef = useRef(false);
  // Debounce machinery for onPaletteChange (leading-edge + trailing).
  const changeTimerRef = useRef(null);
  const lastChangeFireRef = useRef(0);

  // onPaletteChange — fires on the leading edge of an edit burst, then
  // debounces trailing edits at 250 ms (so the worker preview stays in sync
  // without blasting it every keystroke).
  const fireChangeDebounced = useCallback(
    (draft) => {
      if (!onPaletteChange) return;
      const now = Date.now();
      const elapsed = now - lastChangeFireRef.current;
      if (elapsed >= 250) {
        lastChangeFireRef.current = now;
        onPaletteChange(draft);
        return;
      }
      // Within the burst window — schedule trailing call.
      if (changeTimerRef.current) clearTimeout(changeTimerRef.current);
      changeTimerRef.current = setTimeout(() => {
        lastChangeFireRef.current = Date.now();
        onPaletteChange(draft);
      }, 250 - elapsed);
    },
    [onPaletteChange],
  );

  useEffect(() => {
    return () => {
      if (changeTimerRef.current) clearTimeout(changeTimerRef.current);
    };
  }, []);

  const draft = useMemo(() => ({ label, entries }), [label, entries]);

  // Notify parent of edits (debounced). Skip the first mount-fire.
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    fireChangeDebounced(draft);
    // Any user edit re-arms the submit button (after a successful prior save).
    setDidSubmitOnce(false);
  }, [draft, fireChangeDebounced]);

  const updateEntry = (index, patch) => {
    setEntries((prev) => prev.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  };

  const handleLabelChange = (e) => {
    const raw = e.target.value;
    const cleaned = sanitizeLabel(raw);
    let next = cleaned;
    if (cleaned.length > LABEL_MAX) {
      next = cleaned.slice(0, LABEL_MAX);
      toast.error('Label truncated to 32 characters');
    }
    setLabel(next);
    if (next === '') {
      setLabelError(null);
      return;
    }
    if (!LABEL_CHARSET.test(next)) {
      setLabelError('Letters, numbers, _- only');
    } else {
      setLabelError(null);
    }
  };

  const validateHexAt = (index, raw) => {
    if (raw === '' || isValidHex(raw)) {
      setHexErrors((prev) => {
        const next = { ...prev };
        delete next[index];
        return next;
      });
      return true;
    }
    setHexErrors((prev) => ({ ...prev, [index]: 'Use #RRGGBB' }));
    return false;
  };

  const handleHexChange = (index, e) => {
    const raw = e.target.value;
    updateEntry(index, { target_hex: raw });
    validateHexAt(index, raw);
  };

  const handlePasteIntoHex = (index, ev) => {
    const text = ev?.clipboardData?.getData?.('text');
    if (!text) return;
    const tokens = text
      .split(HEX_PASTE_SPLIT)
      .map((s) => s.trim())
      .filter(Boolean);

    if (tokens.length === 0) return;

    if (tokens.length === 1) {
      const t = tokens[0];
      const { value, stripped } = stripAlphaHex(t);
      ev.preventDefault();
      if (stripped) toast('Alpha channel stripped', { icon: '⚠' });
      updateEntry(index, { target_hex: value });
      validateHexAt(index, value);
      return;
    }

    ev.preventDefault();
    setEntries((prev) => {
      const out = [...prev];
      tokens.forEach((tok, i) => {
        const targetIdx = index + i;
        if (targetIdx >= maxEntries) return;
        const { value } = stripAlphaHex(tok);
        out[targetIdx] = { source_hex: null, target_hex: value };
      });
      while (out.length > maxEntries) out.pop();
      return out;
    });
    setHexErrors({});
  };

  // Paste into the label field — if it looks like a list of hexes, populate
  // the entry rows; otherwise let the default paste happen.
  const handleLabelPaste = (ev) => {
    const text = ev?.clipboardData?.getData?.('text');
    if (!text) return;
    const tokens = text
      .split(HEX_PASTE_SPLIT)
      .map((s) => s.trim())
      .filter(Boolean);
    const hexLike = tokens.length > 0 && tokens.every(isValidHex);
    if (!hexLike) return; // default paste (sanitized via onChange)

    if (tokens.length === 1) {
      // Treat as alpha-strippable hex on entry 0.
      ev.preventDefault();
      const { value, stripped } = stripAlphaHex(tokens[0]);
      if (stripped) toast('Alpha channel stripped', { icon: '⚠' });
      setEntries((prev) => {
        const out = [...prev];
        out[0] = { source_hex: null, target_hex: value };
        return out;
      });
      setHexErrors({});
      return;
    }

    ev.preventDefault();
    setEntries(() => {
      const out = [];
      tokens.slice(0, maxEntries).forEach((tok) => {
        const { value } = stripAlphaHex(tok);
        out.push({ source_hex: null, target_hex: value });
      });
      return out;
    });
    setHexErrors({});
  };

  const addEntry = () => {
    if (entries.length >= maxEntries) return;
    setEntries((prev) => [...prev, makeEntry()]);
  };

  const removeEntry = (index) => {
    if (entries.length <= minEntries) return;
    setEntries((prev) => prev.filter((_, i) => i !== index));
    setHexErrors((prev) => {
      const next = { ...prev };
      delete next[index];
      return next;
    });
  };

  const allHexValid = entries.every((e) => isValidHex(e.target_hex));
  const labelValid = !labelError;
  const canSubmit =
    !disabled &&
    !isSubmitting &&
    !didSubmitOnce &&
    entries.length >= minEntries &&
    allHexValid &&
    labelValid;

  const onSubmit = async (e) => {
    e?.preventDefault?.();
    // Synchronous double-submit guard.
    if (submittingRef.current) return;
    if (didSubmitOnce) return;
    if (!canSubmit) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      const payload = {
        label: label || 'untitled',
        entries: entries.map((entry) => ({
          source_hex: entry.source_hex,
          target_hex: normalizeHex(entry.target_hex),
        })),
      };
      const result = await api.createPalette(payload);
      setDidSubmitOnce(true);
      onPaletteCreated?.(result);
      toast.success('Palette saved');
    } catch (err) {
      const status = err?.status;
      if (status === 422) {
        toast.error('Could not save palette');
      } else if (status === 503) {
        toast.error('Server unavailable, retry in a moment');
      } else {
        toast.error(err?.message || 'Could not save palette');
      }
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className={`bg-paper-2 border border-rule rounded-lg p-5 space-y-4 ${className}`}
      aria-label="Palette setup"
    >
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-[17px] tracking-tight text-ink">
          Palette
        </h3>
        <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
          {entries.length} / {maxEntries}
        </span>
      </div>

      <div className="space-y-2">
        {entries.map((entry, idx) => {
          const hexValid = isValidHex(entry.target_hex);
          const hexErr = hexErrors[idx];
          return (
            <div
              key={idx}
              className="flex items-center gap-2"
              data-testid={`palette-row-${idx}`}
            >
              <input
                type="color"
                aria-label={`Pick color ${idx + 1}`}
                value={hexValid ? entry.target_hex : DEFAULT_TARGET}
                onChange={(e) => handleHexChange(idx, { target: { value: e.target.value.toUpperCase() } })}
                disabled={disabled || isSubmitting}
                className="w-7 h-7 rounded-md border border-rule shrink-0 cursor-pointer disabled:cursor-not-allowed appearance-none p-0 overflow-hidden"
                style={{
                  backgroundColor: hexValid ? entry.target_hex : 'transparent',
                }}
                title="Click to open color picker"
              />
              <input
                type="text"
                aria-label={`Target hex ${idx + 1}`}
                value={entry.target_hex}
                onChange={(e) => handleHexChange(idx, e)}
                onPaste={(e) => handlePasteIntoHex(idx, e)}
                disabled={disabled || isSubmitting}
                placeholder="#FF0018"
                aria-invalid={!!hexErr}
                aria-describedby={hexErr ? `hex-error-${idx}` : undefined}
                className={`flex-1 bg-paper border rounded-md px-3 py-1.5 text-[13px] font-mono uppercase text-ink
                  focus:outline-none focus:ring-2 focus:ring-clay/30 focus:border-clay
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${hexErr ? 'border-bad' : 'border-rule'}`}
              />
              <button
                type="button"
                onClick={() => removeEntry(idx)}
                disabled={disabled || isSubmitting || entries.length <= minEntries}
                aria-label={`Remove color ${idx + 1}`}
                className="shrink-0 w-7 h-7 flex items-center justify-center rounded-md
                  text-ink-3 hover:text-bad hover:bg-bad-bg
                  disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-ink-3
                  transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
        {Object.entries(hexErrors).map(([idx, msg]) => (
          <p
            id={`hex-error-${idx}`}
            key={idx}
            className="text-[11px] text-bad font-mono"
            role="alert"
          >
            {msg}
          </p>
        ))}
      </div>

      <div>
        <label
          htmlFor="palette-label-input"
          className="block text-[11px] font-mono tracking-widest uppercase text-ink-3 mb-1.5"
        >
          Label
        </label>
        <input
          id="palette-label-input"
          type="text"
          value={label}
          onChange={handleLabelChange}
          onPaste={handleLabelPaste}
          disabled={disabled || isSubmitting}
          placeholder="chicago"
          aria-invalid={!!labelError}
          aria-describedby={labelError ? 'palette-label-error' : undefined}
          className={`w-full bg-paper border rounded-md px-3 py-2 text-[13px] font-mono text-ink
            placeholder:text-ink-4
            focus:outline-none focus:ring-2 focus:ring-clay/30 focus:border-clay
            disabled:opacity-50 disabled:cursor-not-allowed
            ${labelError ? 'border-bad' : 'border-rule'}`}
        />
        {labelError && (
          <p
            id="palette-label-error"
            className="mt-1 text-[11px] text-bad font-mono"
            role="alert"
          >
            {labelError}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={addEntry}
          disabled={disabled || isSubmitting || entries.length >= maxEntries}
          aria-label="Add color"
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-ink-2
            hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Add color
        </button>

        <button
          type="submit"
          disabled={!canSubmit}
          aria-disabled={!canSubmit}
          aria-label="Save palette"
          className="btn-press inline-flex items-center gap-2 px-4 py-2 rounded-md
            bg-ink text-paper text-[13px] font-medium
            hover:bg-[#2B2B2B] disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors"
        >
          <Save className="w-3.5 h-3.5" />
          {isSubmitting ? 'Saving…' : didSubmitOnce ? 'Saved' : 'Save palette'}
        </button>
      </div>
    </form>
  );
}
