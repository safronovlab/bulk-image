/**
 * ColorStudioTab.jsx — single-design click-fix studio (REWRITTEN in v2).
 *
 * Composes PalettePanel and ClickFixCanvas; v2 removes the v1 per-pair
 * tolerance system and Mode A / Mode B toggle.
 *
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { AlertTriangle, ImageIcon } from 'lucide-react';
import { api } from '../api';
import { parseHex } from '../lib/colorMath';
import PalettePanel from './PalettePanel';
import ClickFixCanvas from './ClickFixCanvas';

const DEFAULT_TARGET_HEX = '#FF0018';

export default function ColorStudioTab({
  selectedImageId,
  setSelectedImageId,
  uploadedImages = [],
  currentPalette = null,
  onPaletteCreated,
  onPaletteChange,
  onResultImageReplaced,
  className = '',
}) {
  const [clusters, setClusters] = useState(null);
  const [clusterError, setClusterError] = useState(null);
  const [selectedTargetIndex, setSelectedTargetIndex] = useState(0);
  const [pending, setPending] = useState(false);

  const fetchAbortRef = useRef(null);

  const targetHex =
    currentPalette?.entries?.[selectedTargetIndex]?.target_hex ||
    currentPalette?.entries?.[0]?.target_hex ||
    DEFAULT_TARGET_HEX;

  const targetRgb = useMemo(() => {
    try {
      return parseHex(targetHex);
    } catch {
      return [255, 0, 24];
    }
  }, [targetHex]);

  const selectedImage = useMemo(
    () => uploadedImages.find((i) => i.image_id === selectedImageId) || null,
    [uploadedImages, selectedImageId],
  );

  const previewUrl = selectedImageId
    ? api.getImagePreviewUrl(selectedImageId)
    : null;

  // Load clusters on selectedImageId change.
  useEffect(() => {
    if (!selectedImageId) {
      setClusters(null);
      setClusterError(null);
      return undefined;
    }
    if (fetchAbortRef.current) {
      try { fetchAbortRef.current.abort(); } catch { /* noop */ }
    }
    let cancelled = false;
    setClusters(null);
    setClusterError(null);

    Promise.resolve(api.getClusters(selectedImageId))
      .then((res) => {
        if (cancelled) return;
        setClusters(res?.clusters || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setClusterError(err?.message || 'Could not load clusters');
        toast.error('Could not load clusters for this design');
      });

    return () => {
      cancelled = true;
    };
  }, [selectedImageId]);

  const handleFixSubmitted = (result) => {
    setPending(false);
    if (!result) return;
    toast.success('Region recolored');
    onResultImageReplaced?.(result.image_id, result.previous_image_id);
  };

  const handleFixError = (err) => {
    setPending(false);
    if (!err) return;
    toast.error(err.message || 'Click-fix failed');
  };

  if (!selectedImageId) {
    if (uploadedImages.length === 0) {
      return (
        <div
          className={`bg-paper-2 border border-rule rounded-lg p-10 text-center ${className}`}
        >
          <div className="mx-auto w-10 h-10 rounded-md bg-paper-3 border border-rule flex items-center justify-center mb-4">
            <ImageIcon className="w-4 h-4 text-ink-3" />
          </div>
          <h2 className="font-display text-2xl text-ink leading-tight">
            No designs yet
          </h2>
          <p className="mt-2 text-[13px] text-ink-2 max-w-md mx-auto leading-relaxed">
            Upload a PNG on the Upload tab. Studio works on one design at a
            time — click-fix recolors the connected region under your cursor.
          </p>
        </div>
      );
    }
    return (
      <div className={className}>
        <header className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-2xl text-ink leading-tight">
            Pick a design
          </h2>
          <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
            {uploadedImages.length} uploaded
          </span>
        </header>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {uploadedImages.map((img) => (
            <button
              key={img.image_id}
              type="button"
              onClick={() => setSelectedImageId?.(img.image_id)}
              className="group relative aspect-square overflow-hidden rounded-md border border-rule bg-paper-2 hover:border-clay-soft btn-press"
              title={img.filename || img.image_id}
            >
              <img
                src={api.getPreviewUrl(img.image_id)}
                alt={img.filename || img.image_id}
                loading="lazy"
                className="absolute inset-0 w-full h-full object-cover"
              />
              <span className="absolute inset-x-0 bottom-0 px-2 py-1 bg-paper/85 backdrop-blur-sm border-t border-rule font-mono text-[10px] text-ink-2 truncate">
                {(img.filename || img.image_id).slice(0, 28)}
              </span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const safeWidth = selectedImage?.width || 1024;
  const safeHeight = selectedImage?.height || 1024;

  return (
    <div className={`grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 ${className}`}>
      <section className="space-y-4">
        <header className="flex items-baseline justify-between gap-3">
          <h2 className="font-display text-2xl text-ink leading-tight">
            Click-fix studio
          </h2>
          <div className="flex items-center gap-3">
            {uploadedImages.length > 1 && setSelectedImageId && (
              <button
                type="button"
                onClick={() => setSelectedImageId(null)}
                className="font-mono text-[10px] tracking-widest uppercase text-ink-3 hover:text-clay-deep underline-offset-2 hover:underline btn-press"
              >
                ← Pick another
              </button>
            )}
            <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
              {selectedImage?.filename || selectedImage?.original_filename || selectedImageId.slice(0, 8)}
            </span>
          </div>
        </header>

        <div className="bg-paper-2 border border-rule rounded-lg p-4">
          {previewUrl ? (
            <ClickFixCanvas
              key={selectedImageId}
              imageId={selectedImageId}
              imageUrl={previewUrl}
              imageWidth={safeWidth}
              imageHeight={safeHeight}
              targetRgb={targetRgb}
              onFixSubmitted={handleFixSubmitted}
              onFixError={handleFixError}
              disabled={pending}
            />
          ) : (
            <div className="text-[12px] text-ink-3 font-mono tracking-wide uppercase text-center py-12">
              No preview
            </div>
          )}
        </div>

        <div className="bg-paper-2 border border-rule rounded-lg p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="font-display text-[15px] text-ink">
              Detected colors
            </h3>
            <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
              read-only
            </span>
          </div>
          {clusterError ? (
            <div
              role="alert"
              className="flex items-center gap-2 text-[12px] text-bad font-mono"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              Could not load clusters — error
            </div>
          ) : clusters === null ? (
            <p className="text-[12px] text-ink-3 font-mono">Loading…</p>
          ) : clusters.length === 0 ? (
            <p className="text-[12px] text-ink-3 font-mono">
              No opaque regions detected.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {clusters.map((c) => (
                <li
                  key={c.cluster_id}
                  className="flex items-center gap-2 px-2 py-1 rounded-md border border-rule bg-paper"
                >
                  <span
                    aria-hidden="true"
                    className="w-4 h-4 rounded-sm border border-rule"
                    style={{ backgroundColor: c.hex }}
                  />
                  <span className="font-mono text-[11px] text-ink">{c.hex}</span>
                  <span className="font-mono text-[10px] text-ink-3">
                    {Math.round((c.percentage || 0) * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {currentPalette?.entries?.length > 0 && (
          <div className="bg-paper-2 border border-rule rounded-lg p-4">
            <div className="flex items-baseline justify-between mb-3">
              <h3 className="font-display text-[15px] text-ink">
                Active target
              </h3>
              <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
                {targetHex}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {currentPalette.entries.map((entry, idx) => {
                const active = idx === selectedTargetIndex;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setSelectedTargetIndex(idx)}
                    aria-label={`Use ${entry.target_hex} as fix color`}
                    aria-pressed={active}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md border transition-colors btn-press
                      ${active ? 'border-clay bg-clay-tint text-ink' : 'border-rule bg-paper text-ink-2 hover:border-rule-strong'}`}
                  >
                    <span
                      aria-hidden="true"
                      className="w-4 h-4 rounded-sm border border-rule"
                      style={{ backgroundColor: entry.target_hex }}
                    />
                    <span className="font-mono text-[11px]">{entry.target_hex}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </section>

      <aside className="lg:sticky lg:top-20 self-start">
        <PalettePanel
          initialPalette={currentPalette}
          onPaletteCreated={onPaletteCreated || (() => {})}
          onPaletteChange={onPaletteChange}
        />
      </aside>
    </div>
  );
}
