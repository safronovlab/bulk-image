import { useState, useCallback, useRef, useEffect } from 'react';
import {
  UploadCloud, Loader2, Trash2, CheckCircle2, Files, Wand2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../api';
import AuthImage from './AuthImage';

export default function UploadTab({ images, setImages, dominantColors, setDominantColors }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const fileRef = useRef(null);
  const [hoveredColor, setHoveredColor] = useState(null);
  const [optimisticPreviews, setOptimisticPreviews] = useState({});

  useEffect(() => {
    return () => {
      Object.values(optimisticPreviews).forEach((u) => URL.revokeObjectURL(u));
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.type === 'image/png' || f.type === 'image/jpeg'
    );
    if (files.length > 0) uploadFiles(files);
    else toast.error('Only PNG and JPEG files are accepted');
  }, []);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) uploadFiles(files);
  };

  const uploadFiles = async (files) => {
    if (files.length > 500) {
      toast.error(`Too many files (${files.length}) — split into batches.`);
      return;
    }
    setUploading(true);
    let succeeded = 0;
    let failed = 0;
    let firstError = null;
    let progressToastId = toast.loading(
      `Uploading 1/${files.length}…`,
      { duration: Infinity },
    );
    // Sequential upload — backend runs K-means per file, parallel storms the
    // worker pool and produces the "very long load" symptom.
    for (let i = 0; i < files.length; i += 1) {
      const f = files[i];
      toast.loading(
        `Uploading ${i + 1}/${files.length} · ${f.name}…`,
        { id: progressToastId },
      );
      try {
        const meta = await api.uploadImage(f);
        const localUrl = URL.createObjectURL(f);
        setOptimisticPreviews((prev) => ({ ...prev, [meta.image_id]: localUrl }));
        setImages((prev) => [...prev, meta]);
        setDominantColors((prev) => ({ ...prev, [meta.image_id]: meta.clusters || [] }));
        succeeded += 1;
      } catch (err) {
        failed += 1;
        firstError = firstError || err;
      }
    }
    toast.dismiss(progressToastId);
    if (succeeded > 0) {
      toast.success(`${succeeded} design${succeeded > 1 ? 's' : ''} uploaded`);
    }
    if (failed > 0) {
      toast.error(
        `${failed} file${failed > 1 ? 's' : ''} failed: ${firstError?.message || 'unknown error'}`,
      );
    }
    setUploading(false);
  };

  const handleAnalyzeAll = async () => {
    if (images.length === 0) {
      toast.error('Upload some designs first');
      return;
    }
    setAnalyzing(true);
    try {
      const settled = await Promise.allSettled(
        images.map((img) =>
          api
            .getImageClusters(img.image_id)
            .then((res) => [img.image_id, res.clusters || []])
        )
      );
      const merged = Object.fromEntries(
        settled.filter((r) => r.status === 'fulfilled').map((r) => r.value)
      );
      setDominantColors((prev) => ({ ...prev, ...merged }));
      toast.success('Color analysis complete');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDelete = async (imageId) => {
    try {
      await api.deleteImage(imageId);
      setImages((prev) => prev.filter((img) => img.image_id !== imageId));
      setOptimisticPreviews((prev) => {
        const url = prev[imageId];
        if (url) URL.revokeObjectURL(url);
        const { [imageId]: _, ...rest } = prev;
        return rest;
      });
      toast.success('Image deleted');
    } catch (err) {
      toast.error(err.message);
    }
  };

  const totalPixels = images.reduce((s, i) => s + (i.width || 0) * (i.height || 0), 0);
  const formatPixels = (px) => {
    if (px >= 1e6) return `${(px / 1e6).toFixed(1)}M`;
    if (px >= 1e3) return `${(px / 1e3).toFixed(0)}K`;
    return String(px);
  };

  return (
    <div className="space-y-7 stagger-children">
      {/* ── Section header ──────────────────────────────────────────── */}
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-ink-3)] mb-1.5">
            Step 01 — Ingest
          </p>
          <h1 className="font-display text-[28px] leading-tight text-[var(--color-ink)] tracking-tight">
            Upload designs
          </h1>
          <p className="text-[13px] text-[var(--color-ink-2)] mt-1.5 max-w-[60ch] leading-relaxed">
            Drop PNG or JPEG files. Originals are preserved exactly — same DPI, resolution, and quality.
            Dominant colors are extracted automatically in the background.
          </p>
        </div>
        {images.length > 0 && (
          <div className="flex items-center gap-4 sm:gap-6 px-4 py-2.5 bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-lg shrink-0">
            <Stat label="Designs" value={images.length} />
            <span className="w-px h-7 bg-[var(--color-rule)]" />
            <Stat label="Pixels" value={formatPixels(totalPixels)} />
            <span className="w-px h-7 bg-[var(--color-rule)]" />
            <Stat label="Analyzed" value={Object.keys(dominantColors).length} />
          </div>
        )}
      </header>

      {/* ── Drop zone ───────────────────────────────────────────────── */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        className={`
          relative rounded-2xl px-8 py-14 text-center cursor-pointer transition-all duration-200
          border border-dashed
          ${dragging
            ? 'border-[var(--color-clay)] bg-[var(--color-clay-tint)]'
            : 'border-[var(--color-rule-strong)] bg-[var(--color-paper-2)] hover:bg-[var(--color-paper-3)]'
          }
        `}
      >
        <input
          ref={fileRef}
          type="file"
          multiple
          accept="image/png,image/jpeg"
          onChange={handleFileSelect}
          className="hidden"
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-3 animate-pulse-soft">
            <Loader2 className="w-9 h-9 text-[var(--color-clay-deep)] animate-spin" />
            <p className="text-[var(--color-ink-2)] text-[13px]">Uploading designs…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3.5">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-200 ${
              dragging
                ? 'bg-[var(--color-clay-soft)] scale-110'
                : 'bg-[var(--color-paper-3)]'
            }`}>
              <UploadCloud className={`w-6 h-6 ${dragging ? 'text-[var(--color-clay-deep)]' : 'text-[var(--color-ink-2)]'}`} />
            </div>
            <div>
              <p className="font-display text-[18px] text-[var(--color-ink)] leading-tight">
                {dragging ? 'Release to upload' : 'Drop designs here'}
              </p>
              <p className="text-[12px] text-[var(--color-ink-3)] mt-1.5 font-mono tracking-tight">
                PNG · JPEG · bulk supported · 300 DPI print-ready
              </p>
            </div>
            <span className="mt-1 px-3.5 py-1.5 bg-[var(--color-paper)] border border-[var(--color-rule)] rounded-md text-[11px] text-[var(--color-ink-2)] font-medium">
              or click to browse
            </span>
          </div>
        )}
      </div>

      {/* ── Action bar ──────────────────────────────────────────────── */}
      {images.length > 0 && (
        <div className="flex items-center justify-between bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-xl px-4 py-3">
          <div className="flex items-center gap-2.5 text-[13px] text-[var(--color-ink-2)]">
            <CheckCircle2 className="w-4 h-4 text-[var(--color-ok)]" />
            <span>
              <span className="font-mono font-semibold text-[var(--color-ink)] tabular-nums">{images.length}</span>
              {' '}design{images.length !== 1 ? 's' : ''} uploaded
            </span>
          </div>
          <button
            onClick={handleAnalyzeAll}
            disabled={analyzing}
            className="btn-press flex items-center gap-2 px-4 py-2 bg-[var(--color-ink)] hover:bg-[#2B2B2B] text-[var(--color-paper)] rounded-md font-medium text-[13px] transition-colors disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {analyzing ? 'Analyzing…' : 'Re-analyze colors'}
          </button>
        </div>
      )}

      {/* ── Image grid ──────────────────────────────────────────────── */}
      {images.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {images.map((img, idx) => (
            <article
              key={img.image_id}
              className="group card-hover bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-xl overflow-hidden"
              style={{
                animationDelay: `${Math.min(idx * 40, 400)}ms`,
                contentVisibility: 'auto',
                containIntrinsicSize: '240px 280px',
              }}
            >
              <div className="relative aspect-square bg-[var(--color-paper)]">
                <AuthImage
                  src={`/api/images/${img.image_id}/preview`}
                  localSrc={optimisticPreviews[img.image_id]}
                  alt={img.filename}
                  className="w-full h-full object-contain p-3"
                  priority={idx < 5}
                />
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(img.image_id); }}
                  className="absolute top-2 right-2 w-7 h-7 bg-[var(--color-paper-2)]/95 backdrop-blur border border-[var(--color-rule)] rounded-md flex items-center justify-center transition-all hover:bg-[var(--color-bad-bg)] hover:border-[var(--color-bad)]/40 hover:text-[var(--color-bad)] text-[var(--color-ink-3)]"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="p-3 border-t border-[var(--color-rule)]">
                <p className="text-[12px] font-medium text-[var(--color-ink)] truncate" title={img.filename}>
                  {img.filename}
                </p>
                <p className="text-[10px] text-[var(--color-ink-3)] mt-1 font-mono tracking-tight tabular-nums">
                  {img.width} × {img.height}
                  {img.original_format ? ` · ${img.original_format.toUpperCase()}` : ''}
                  {img.dpi ? ` · ${img.dpi}dpi` : ''}
                </p>

                {dominantColors[img.image_id] && (
                  <div className="mt-2.5 space-y-1.5 relative">
                    <div className="flex gap-1">
                      {(dominantColors[img.image_id].dominant_colors || dominantColors[img.image_id]).map((c, i) => (
                        <button
                          key={i}
                          className="w-5 h-5 rounded border border-[var(--color-rule)] cursor-pointer hover:scale-110 transition-transform"
                          style={{ backgroundColor: c.hex }}
                          onMouseEnter={() => setHoveredColor({ imageId: img.image_id, index: i })}
                          onMouseLeave={() => setHoveredColor(null)}
                          title={`${c.hex}${c.percentage ? ` · ${c.percentage.toFixed(1)}%` : ''}`}
                        />
                      ))}
                    </div>
                    {hoveredColor?.imageId === img.image_id && (() => {
                      const colors = dominantColors[img.image_id].dominant_colors || dominantColors[img.image_id];
                      const c = colors[hoveredColor.index];
                      if (!c) return null;
                      return (
                        <div className="bg-[var(--color-ink)] text-[var(--color-paper)] text-[10px] font-mono px-2 py-1 rounded inline-block animate-fade-in">
                          {c.hex}{c.percentage ? ` · ${c.percentage.toFixed(1)}%` : ''}
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────── */}
      {images.length === 0 && !uploading && (
        <div className="border border-[var(--color-rule)] border-dashed rounded-2xl px-6 py-16 text-center bg-[var(--color-paper-2)]/40 animate-fade-in">
          <div className="w-12 h-12 rounded-xl bg-[var(--color-paper-3)] flex items-center justify-center mx-auto mb-3">
            <Files className="w-6 h-6 text-[var(--color-ink-3)]" />
          </div>
          <p className="font-display text-[16px] text-[var(--color-ink)]">No designs uploaded yet</p>
          <p className="text-[12px] text-[var(--color-ink-3)] mt-1 max-w-[44ch] mx-auto leading-relaxed">
            Once you upload, designs appear here as a grid with their dominant palette extracted automatically.
          </p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="text-left">
      <p className="text-[9px] font-mono uppercase tracking-[0.14em] text-[var(--color-ink-3)] leading-tight">
        {label}
      </p>
      <p className="font-mono text-[15px] font-semibold text-[var(--color-ink)] tabular-nums leading-tight mt-0.5">
        {value}
      </p>
    </div>
  );
}
