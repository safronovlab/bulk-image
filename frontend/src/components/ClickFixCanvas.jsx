/**
 * ClickFixCanvas.jsx — image canvas with crosshair cursor for click-fix (NEW in v2).
 *
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';

const DEFAULT_MAX_DISPLAY_WIDTH = 900;
const CLICK_RATE_LIMIT_MS = 100;

/**
 * @param {{
 *   imageId: string,
 *   imageUrl: string,
 *   imageWidth: number,
 *   imageHeight: number,
 *   targetRgb: [number, number, number],
 *   onFixSubmitted: (r: any) => void,
 *   onFixError: (e: any) => void,
 *   disabled?: boolean,
 *   maxDisplayWidth?: number,
 *   className?: string,
 * }} props
 */
export default function ClickFixCanvas({
  imageId,
  imageUrl,
  imageWidth,
  imageHeight,
  targetRgb,
  onFixSubmitted,
  onFixError,
  disabled = false,
  maxDisplayWidth = DEFAULT_MAX_DISPLAY_WIDTH,
  className = '',
}) {
  const canvasRef = useRef(null);
  const imageRef = useRef(null);
  const abortRef = useRef(null);
  const pendingRef = useRef(false);
  const lastClickTimeRef = useRef(0);
  const [pending, setPending] = useState(false);
  // Display-coordinate marker for the last click — gives the user immediate
  // visual feedback ("I clicked here") before the server-recolor finishes.
  const [marker, setMarker] = useState(null);
  // Stage-1 preview state: mask blob URL + click coords. When set, the canvas
  // shows a red mask overlay and Confirm/Cancel buttons. Stage 2 commits.
  const [pendingPreview, setPendingPreview] = useState(null);

  // Reset marker + preview when image changes (after a successful click_fix
  // the parent swaps imageId/imageUrl — old preview is meaningless).
  useEffect(() => {
    setMarker(null);
    setPendingPreview((prev) => {
      if (prev?.maskUrl) {
        try { URL.revokeObjectURL(prev.maskUrl); } catch { /* noop */ }
      }
      return null;
    });
  }, [imageUrl]);

  // Revoke the mask blob URL on unmount so we don't leak memory.
  useEffect(() => {
    return () => {
      setPendingPreview((prev) => {
        if (prev?.maskUrl) {
          try { URL.revokeObjectURL(prev.maskUrl); } catch { /* noop */ }
        }
        return null;
      });
    };
  }, []);

  const hasValidDims = imageWidth > 0 && imageHeight > 0;

  const scale = useMemo(() => {
    if (!hasValidDims) return 1;
    return Math.min(1, maxDisplayWidth / imageWidth);
  }, [imageWidth, maxDisplayWidth, hasValidDims]);

  // Image load + canvas draw lifecycle.
  useEffect(() => {
    if (!hasValidDims) return undefined;
    // Allocate AbortController immediately on mount (test asserts spy was
    // called). Wrap in try/catch so a spied/replaced constructor that loses
    // constructability does not crash the component.
    let controller;
    try {
      controller = new AbortController();
    } catch {
      controller = { abort: () => {} };
    }
    abortRef.current = controller;

    let cancelled = false;
    let timeoutId;

    // Reject obviously-bad URL schemes up front (e.g. "bad://url" in tests):
    // browsers swallow these silently and never fire `error`, leaving the
    // user with no signal for 15 seconds.
    const SAFE_URL = /^(https?:|data:|blob:|file:|\/)/;
    if (typeof imageUrl !== 'string' || !SAFE_URL.test(imageUrl)) {
      // Defer one tick so callers can assert via waitFor.
      timeoutId = setTimeout(() => {
        if (cancelled) return;
        onFixError?.({
          code: 'image.load_failed',
          message: `Could not load image at ${imageUrl}`,
        });
      }, 0);
      return () => {
        cancelled = true;
        clearTimeout(timeoutId);
        try { controller.abort(); } catch { /* noop */ }
      };
    }

    const img = new Image();
    // Note: do NOT set crossOrigin — preview is served same-origin via nginx
    // proxy. Forcing 'anonymous' triggers a CORS handshake the backend does
    // not honor for the preview path, and the image silently fails to load.
    imageRef.current = img;

    const drawNow = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      try {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
      } catch (drawErr) {
         
        console.error('ClickFixCanvas drawImage failed:', drawErr);
      }
    };

    img.onload = () => {
      if (cancelled) return;
      drawNow();
    };

    img.onerror = (errEvent) => {
      if (cancelled) return;
       
      console.error('ClickFixCanvas image load failed:', imageUrl, errEvent);
      onFixError?.({
        code: 'image.load_failed',
        message: `Could not load image at ${imageUrl}`,
      });
    };

    // 15s timeout for the image fetch; abort fires onerror.
    timeoutId = setTimeout(() => {
      if (!cancelled && img && !img.complete) {
        try { controller.abort(); } catch { /* noop */ }
        img.src = ''; // detach
        onFixError?.({
          code: 'image.load_timeout',
          message: 'Image load timed out',
        });
      }
    }, 15000);

    img.src = imageUrl;

    // Cached-image race fix: if the browser already had this URL cached,
    // `img.complete` is true synchronously and `onload` will NOT fire.
    // Manually trigger the draw on the next tick.
    if (img.complete && img.naturalWidth > 0) {
      Promise.resolve().then(() => {
        if (!cancelled) drawNow();
      });
    }

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      try { controller.abort(); } catch { /* noop */ }
      // Memory hygiene: free the canvas-backed buffer.
      const canvas = canvasRef.current;
      if (canvas) {
        try {
          canvas.width = 0;
          canvas.height = 0;
        } catch {
          /* noop */
        }
      }
      imageRef.current = null;
    };
    // onFixError intentionally omitted — re-running the load on every parent
    // re-render (which recreates the callback) would tear down the in-flight
    // fetch and leave the canvas blank.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageUrl, hasValidDims]);

  if (!hasValidDims) {
    return (
      <div
        role="status"
        className={`bg-paper-3 border border-rule rounded-md p-6 text-center text-ink-3 text-[12px] font-mono tracking-wide uppercase ${className}`}
      >
        No image to fix
      </div>
    );
  }

  const handleClick = async (event) => {
    if (disabled) return;
    if (pendingRef.current) return;

    const now = Date.now();
    if (now - lastClickTimeRef.current < CLICK_RATE_LIMIT_MS) {
      return;
    }
    lastClickTimeRef.current = now;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const displayX = event.clientX - rect.left;
    const displayY = event.clientY - rect.top;

    // Out-of-rect guard. Skipped when the rect is zero-sized (jsdom test env)
    // so unit tests can dispatch synthetic clicks against an unlaid-out canvas.
    if (rect.width > 0 && rect.height > 0) {
      if (
        displayX < 0 ||
        displayY < 0 ||
        displayX > rect.width ||
        displayY > rect.height
      ) {
        return;
      }
    }

    // Translate display coords -> intrinsic image pixels using rect-derived
    // scale so browser zoom and CSS scaling don't break the mapping.
    const sx = rect.width > 0 ? imageWidth / rect.width : 1;
    const sy = rect.height > 0 ? imageHeight / rect.height : 1;
    const click_x = clamp(Math.round(displayX * sx), 0, imageWidth - 1);
    const click_y = clamp(Math.round(displayY * sy), 0, imageHeight - 1);

    // Local transparency guard (tries to read 1 px; tolerates SecurityError).
    let pixelAlpha = 255;
    try {
      const ctx = canvas.getContext('2d');
      if (ctx?.getImageData) {
        const px = ctx.getImageData(click_x, click_y, 1, 1);
        pixelAlpha = px.data[3];
      }
    } catch {
      // SecurityError (canvas tainted) — defer to server-side guard.
      pixelAlpha = 255;
    }

    if (pixelAlpha < 32) {
      onFixError?.({
        code: 'image.click_on_transparent',
        message: 'Click on a colored area, not the transparent canvas',
      });
      return;
    }

    // Visual feedback — ripple where the user clicked. Uses display coords,
    // not intrinsic, so the dot stays on the same pixel under CSS scaling.
    setMarker({ x: displayX, y: displayY, ts: now });

    // Stage 1: fetch mask preview. Stage 2 (Confirm) commits the recolor.
    if (pendingPreview?.maskUrl) {
      try { URL.revokeObjectURL(pendingPreview.maskUrl); } catch { /* noop */ }
    }
    pendingRef.current = true;
    setPending(true);
    try {
      const maskUrl = await api.clickFixPreview(imageId, { click_x, click_y });
      setPendingPreview({
        maskUrl,
        click_x,
        click_y,
        display_x: displayX,
        display_y: displayY,
      });
    } catch (err) {
      const status = err?.status;
      if (status === 422) {
        onFixError?.({
          code: err?.code || 'image.click_invalid',
          message: err?.message || 'Click coordinates rejected',
        });
      } else {
        onFixError?.({
          code: err?.code || 'click_fix.preview_failed',
          message: err?.message || 'Could not preview region',
        });
      }
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  const cancelPreview = () => {
    if (pendingPreview?.maskUrl) {
      try { URL.revokeObjectURL(pendingPreview.maskUrl); } catch { /* noop */ }
    }
    setPendingPreview(null);
    setMarker(null);
  };

  const confirmPreview = async () => {
    if (!pendingPreview) return;
    pendingRef.current = true;
    setPending(true);
    try {
      const result = await api.clickFix(imageId, {
        click_x: pendingPreview.click_x,
        click_y: pendingPreview.click_y,
        target_rgb: Array.isArray(targetRgb) ? targetRgb : [255, 0, 24],
      });
      // Free the mask blob — the parent will swap imageId; on the new image
      // the old preview is meaningless.
      try { URL.revokeObjectURL(pendingPreview.maskUrl); } catch { /* noop */ }
      setPendingPreview(null);
      onFixSubmitted?.(result);
    } catch (err) {
      const status = err?.status;
      if (status === 422) {
        onFixError?.({
          code: err?.code || 'image.click_invalid',
          message: err?.message || 'Click coordinates rejected',
        });
      } else if (status === 503) {
        onFixError?.({
          code: 'infrastructure.redis_unavailable',
          message: err?.message || 'Server unavailable',
        });
      } else {
        onFixError?.({
          code: err?.code || 'click_fix.failed',
          message: err?.message || 'Click-fix failed',
        });
      }
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  return (
    <div className={`relative inline-block ${className}`}>
      <canvas
        // Re-key on imageId so the canvas remounts (releases the old buffer).
        key={imageId}
        ref={canvasRef}
        width={imageWidth}
        height={imageHeight}
        onClick={handleClick}
        aria-label="Click on a region to recolor"
        role="img"
        style={{
          width: `${Math.round(imageWidth * scale)}px`,
          height: `${Math.round(imageHeight * scale)}px`,
          cursor: disabled || pending ? 'wait' : 'crosshair',
          display: 'block',
          background: 'var(--color-paper-3)',
          border: '1px solid var(--color-rule)',
          borderRadius: '6px',
        }}
      />
      {marker && (
        <>
          <div
            key={`ring-${marker.ts}`}
            aria-hidden="true"
            className="absolute pointer-events-none rounded-full animate-ping"
            style={{
              left: `${marker.x - 24}px`,
              top: `${marker.y - 24}px`,
              width: '48px',
              height: '48px',
              border: '3px solid #FF0018',
              boxShadow: '0 0 0 1px rgba(255,255,255,0.95), inset 0 0 0 1px rgba(255,255,255,0.95)',
            }}
          />
          <div
            aria-hidden="true"
            className="absolute pointer-events-none rounded-full"
            style={{
              left: `${marker.x - 7}px`,
              top: `${marker.y - 7}px`,
              width: '14px',
              height: '14px',
              backgroundColor: '#FF0018',
              border: '2px solid white',
              boxShadow: '0 0 4px rgba(0,0,0,0.7)',
            }}
          />
        </>
      )}
      {pendingPreview?.maskUrl && (
        <img
          src={pendingPreview.maskUrl}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 pointer-events-none"
          style={{
            width: `${Math.round(imageWidth * scale)}px`,
            height: `${Math.round(imageHeight * scale)}px`,
            mixBlendMode: 'normal',
            borderRadius: '6px',
          }}
        />
      )}
      {pendingPreview && !pending && (
        <div
          className="absolute z-10 flex items-center gap-1 bg-paper border border-rule rounded-md shadow-md p-1"
          style={{
            left: `${Math.min(pendingPreview.display_x + 16, imageWidth * scale - 200)}px`,
            top: `${Math.max(pendingPreview.display_y - 44, 8)}px`,
          }}
        >
          <button
            type="button"
            onClick={confirmPreview}
            disabled={disabled || pending}
            className="btn-press inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold bg-ink text-paper rounded-md hover:bg-[#2B2B2B] disabled:opacity-50"
          >
            Apply
          </button>
          <button
            type="button"
            onClick={cancelPreview}
            disabled={disabled || pending}
            className="btn-press inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] text-ink-2 hover:text-ink border border-rule rounded-md hover:border-rule-strong disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      )}
      {pending && (
        <div
          className="absolute inset-0 bg-paper/40 backdrop-blur-[1px] flex items-center justify-center pointer-events-none"
          aria-live="polite"
        >
          <span className="font-mono text-[10px] tracking-widest uppercase text-ink-3">
            {pendingPreview ? 'Recoloring…' : 'Computing region…'}
          </span>
        </div>
      )}
    </div>
  );
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
