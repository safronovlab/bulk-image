/**
 * BatchProcessTab.jsx — palette-based bulk recolor (REWRITTEN in v2).
 *
 * Drives the Apply All flow over all uploaded designs and instantiates the
 * preview Web Worker for instant client-side feedback. v2 removes the
 * v1 Mode A / Mode B toggle and per-image tolerance sliders.
 *
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Play, Image as ImageIcon, AlertTriangle } from 'lucide-react';
import { api } from '../api';
import PalettePanel from './PalettePanel';

const MAX_BATCH_SIZE = 20;

function previewUrlFor(imageId) {
  if (typeof api?.getImagePreviewUrl === 'function') {
    return api.getImagePreviewUrl(imageId);
  }
  return `/api/images/${imageId}/preview`;
}

// LRU-capped preview cache helper.
function cappedSet(map, key, value, cap) {
  const next = new Map(map);
  if (next.has(key)) next.delete(key);
  next.set(key, value);
  while (next.size > cap) {
    const oldest = next.keys().next().value;
    next.delete(oldest);
  }
  return next;
}

let correlationCounter = 0;
function nextCorrelationId() {
  correlationCounter += 1;
  return `c${Date.now()}-${correlationCounter}`;
}

export default function BatchProcessTab({
  uploadedImages = [],
  currentPalette = null,
  onPaletteCreated,
  onJobSubmitted,
  disabled = false,
  className = '',
}) {
  const [jobSubmitting, setJobSubmitting] = useState(false);
  const [workerReady, setWorkerReady] = useState(false);
  const [workerFailed, setWorkerFailed] = useState(false);
  const [previewByImageId, setPreviewByImageId] = useState(new Map());
  const [selectedThumbnailId, setSelectedThumbnailId] = useState(null);

  const workerRef = useRef(null);
  const submittingRef = useRef(false);
  const lastCorrelationRef = useRef(null);

  const activeImages = useMemo(
    () => uploadedImages.slice(0, MAX_BATCH_SIZE),
    [uploadedImages],
  );

  // Spin up worker once.
  useEffect(() => {
    let worker = null;
    try {
      worker = new Worker(
        new URL('../workers/preview.worker.js', import.meta.url),
        { type: 'module' },
      );
      workerRef.current = worker;
      const onMessage = (e) => {
        const data = e?.data || {};
        if (data.type === 'PREVIEW_RESULT') {
          setPreviewByImageId((prev) =>
            cappedSet(prev, data.image_id, data.data_url, MAX_BATCH_SIZE),
          );
        } else if (data.type === 'PREVIEW_ERROR') {
          // Non-blocking: previews are an enhancement (FR-P4).
          if (data.code === 'worker.unsupported') {
            setWorkerFailed(true);
          }
        }
      };
      const onError = () => setWorkerFailed(true);
      worker.addEventListener?.('message', onMessage);
      worker.addEventListener?.('error', onError);
      worker.addEventListener?.('messageerror', onError);
      // Some test mocks attach handlers via .onmessage too.
      worker.onmessage = onMessage;
      worker.onerror = onError;
      setWorkerReady(true);
    } catch {
      setWorkerFailed(true);
      setWorkerReady(false);
    }

    return () => {
      try {
        if (lastCorrelationRef.current && worker?.postMessage) {
          worker.postMessage({
            type: 'CANCEL',
            correlationId: lastCorrelationRef.current,
          });
        }
      } catch {
        /* noop */
      }
      try { worker?.terminate?.(); } catch { /* noop */ }
      workerRef.current = null;
    };
  }, []);

  // PalettePanel onPaletteChange — dispatch to worker (debounced inside the panel).
  const handlePaletteChange = (draft) => {
    if (!workerReady || workerFailed) return;
    if (!draft?.entries?.length) return;
    // Skip drafts with invalid hexes — leave the previous valid preview visible.
    const allValid = draft.entries.every(
      (e) => /^#?[0-9A-Fa-f]{3}$|^#?[0-9A-Fa-f]{6}$/.test((e.target_hex || '').trim()),
    );
    if (!allValid) return;

    // Cancel previous request before sending the new one.
    if (lastCorrelationRef.current && workerRef.current?.postMessage) {
      try {
        workerRef.current.postMessage({
          type: 'CANCEL',
          correlationId: lastCorrelationRef.current,
        });
      } catch {
        /* noop */
      }
    }
    const correlationId = nextCorrelationId();
    lastCorrelationRef.current = correlationId;
    try {
      workerRef.current.postMessage({
        type: 'PREVIEW_REQUEST',
        correlationId,
        images: activeImages.map((img) => ({
          image_id: img.image_id,
          preview_url: previewUrlFor(img.image_id),
        })),
        palette: draft,
      });
    } catch {
      /* noop — worker will error out via onError */
    }
  };

  const handleApplyAll = async () => {
    if (submittingRef.current) return;
    if (jobSubmitting) return;
    if (!currentPalette) {
      toast('Save a palette first', { icon: 'i' });
      return;
    }
    if (activeImages.length === 0) {
      toast.error('Upload PNGs first');
      return;
    }
    submittingRef.current = true;
    setJobSubmitting(true);
    try {
      const result = await api.submitRecolorJob({
        image_ids: activeImages.map((i) => i.image_id),
        palette_id: currentPalette.palette_id,
      });
      onJobSubmitted?.(result);
      toast.success('Job queued');
    } catch (err) {
      const status = err?.status;
      if (status === 422) {
        toast.error(err?.message || 'Could not submit batch');
      } else if (status === 503) {
        toast.error('Server unavailable, retry in a moment');
      } else {
        toast.error(err?.message || 'Could not submit batch');
      }
    } finally {
      submittingRef.current = false;
      setJobSubmitting(false);
    }
  };

  const canApply =
    !disabled &&
    !jobSubmitting &&
    activeImages.length > 0 &&
    !!currentPalette;

  return (
    <div className={`grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 ${className}`}>
      <section className="space-y-4">
        <header className="flex items-baseline justify-between">
          <h2 className="font-display text-2xl text-ink leading-tight">
            Apply palette to all
          </h2>
          <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
            {activeImages.length} / {MAX_BATCH_SIZE}
          </span>
        </header>

        {workerFailed && (
          <div
            role="status"
            className="flex items-center gap-2 px-3 py-2 border border-rule bg-paper-3 rounded-md text-[12px] text-ink-2 font-mono"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-warn" />
            Live preview disabled — server output is unaffected.
          </div>
        )}

        {/* Thumbnail strip */}
        {activeImages.length === 0 ? (
          <div className="bg-paper-2 border border-rule rounded-lg p-10 text-center">
            <div className="mx-auto w-10 h-10 rounded-md bg-paper-3 border border-rule flex items-center justify-center mb-4">
              <ImageIcon className="w-4 h-4 text-ink-3" />
            </div>
            <p className="font-display text-xl text-ink">No designs uploaded</p>
            <p className="mt-2 text-[12px] text-ink-3 font-mono">
              Drop PNGs in the Upload tab to begin.
            </p>
          </div>
        ) : (
          <ul
            className="grid gap-3"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}
            aria-label="Uploaded designs"
          >
            {activeImages.map((img) => {
              const preview = previewByImageId.get(img.image_id);
              const previewSrc = preview || previewUrlFor(img.image_id);
              const selected = selectedThumbnailId === img.image_id;
              return (
                <li key={img.image_id}>
                  <button
                    type="button"
                    onClick={() => setSelectedThumbnailId(img.image_id)}
                    className={`group block w-full text-left rounded-md border bg-paper-2 overflow-hidden card-hover transition-colors
                      ${selected ? 'border-clay shadow-[inset_0_0_0_1px_var(--color-clay)]' : 'border-rule hover:border-rule-strong'}`}
                  >
                    <div className="aspect-square bg-paper-3 flex items-center justify-center overflow-hidden">
                      <img
                        src={previewSrc}
                        alt={img.original_filename || img.image_id}
                        className="w-full h-full object-contain thumb-fade-in"
                        loading="lazy"
                      />
                    </div>
                    <div className="px-2 py-1.5 text-[11px] font-mono truncate text-ink">
                      {img.original_filename || img.image_id.slice(0, 8)}
                    </div>
                    <div className="px-2 pb-1.5 text-[10px] font-mono text-ink-3">
                      {img.width}×{img.height}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="text-[12px] text-ink-3 font-mono">
            {currentPalette
              ? `Palette: ${currentPalette.label || 'untitled'} · ${currentPalette.entries?.length || 0} colors`
              : 'No palette saved yet'}
          </p>

          <button
            type="button"
            onClick={handleApplyAll}
            disabled={!canApply}
            aria-disabled={!canApply}
            aria-label={`Apply All to ${activeImages.length} designs`}
            className="btn-press inline-flex items-center gap-2 px-5 py-2.5 rounded-md
              bg-ink text-paper text-[13px] font-medium
              hover:bg-[#2B2B2B] disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            {jobSubmitting
              ? 'Submitting…'
              : `Apply All to ${activeImages.length} designs`}
          </button>
        </div>
      </section>

      <aside className="lg:sticky lg:top-20 self-start">
        <PalettePanel
          initialPalette={currentPalette}
          onPaletteCreated={onPaletteCreated || (() => {})}
          onPaletteChange={handlePaletteChange}
        />
      </aside>
    </div>
  );
}
