/**
 * preview.worker.js — Web Worker for instant client-side recolor preview (NEW in v2).
 *
 *
 * Message protocol (inbound): PREVIEW_REQUEST, CANCEL.
 * Message protocol (outbound): PREVIEW_RESULT, PREVIEW_ERROR.
 */

import { parseHex, rgbToLab, deltaE2000 } from '../lib/colorMath.js';

// Per-image active correlation map; second request for same image cancels first.
const activeByImageId = new Map(); // image_id -> { correlationId, controller }
// Per-correlation aborts; CANCEL message uses this.
const controllerByCorrelation = new Map(); // correlationId -> AbortController

// Validate the preview URL is same-origin and matches /api/images/{id}/preview.
// The check is light — defends against accidental URL leakage.
const PREVIEW_URL_PATTERN = /^\/api\/images\/[A-Za-z0-9_-]+\/preview(?:\?.*)?$/;

function postError(correlationId, image_id, code, message) {
   
  self.postMessage({
    type: 'PREVIEW_ERROR',
    correlationId,
    image_id,
    code,
    message,
  });
}

function isOffscreenCanvasSupported() {
  return typeof OffscreenCanvas !== 'undefined';
}

let unsupportedNoticeSent = false;

async function handlePreviewRequest(message) {
  const { correlationId, images, palette, delta_e_threshold = 25.0 } = message;

  if (!isOffscreenCanvasSupported()) {
    if (!unsupportedNoticeSent) {
      unsupportedNoticeSent = true;
      postError(
        correlationId,
        null,
        'worker.unsupported',
        'OffscreenCanvas not available',
      );
    }
    return;
  }

  // Validate palette up front; per spec one PREVIEW_ERROR if entirely invalid.
  let paletteEntries;
  try {
    paletteEntries = (palette?.entries || []).map((e) => {
      const targetRgb = parseHex(e.target_hex);
      const sourceRgb = e.source_hex ? parseHex(e.source_hex) : targetRgb;
      return {
        target_rgb: targetRgb,
        source_lab: rgbToLab(sourceRgb),
      };
    });
    if (paletteEntries.length === 0) {
      throw new RangeError('palette has no entries');
    }
  } catch (err) {
    postError(
      correlationId,
      null,
      'palette.invalid',
      err?.message || 'Invalid palette',
    );
    return;
  }

  if (!Array.isArray(images) || images.length === 0) {
    return;
  }

  // Each request gets its own controller; CANCEL aborts via this.
  const controller = new AbortController();
  controllerByCorrelation.set(correlationId, controller);

  try {
    for (const img of images) {
      const { image_id, preview_url } = img;

      // Drop earlier in-flight request for the same image_id.
      const prior = activeByImageId.get(image_id);
      if (prior && prior.correlationId !== correlationId) {
        prior.controller?.abort();
      }
      activeByImageId.set(image_id, { correlationId, controller });

      // Reject off-origin / malformed preview URLs (security guard).
      if (!PREVIEW_URL_PATTERN.test(preview_url)) {
        postError(
          correlationId,
          image_id,
          'image.fetch_failed',
          'preview_url did not match /api/images/{id}/preview',
        );
        continue;
      }

      const start = (typeof performance !== 'undefined' ? performance.now() : Date.now());

      let blob;
      try {
        const res = await fetch(preview_url, { signal: controller.signal });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        blob = await res.blob();
      } catch (err) {
        if (err?.name === 'AbortError') {
          return; // CANCEL or new request preempted us.
        }
        postError(correlationId, image_id, 'image.fetch_failed', String(err?.message || err));
        continue;
      }

      let bitmap;
      try {
        bitmap = await createImageBitmap(blob);
      } catch (err) {
        postError(correlationId, image_id, 'image.decode_failed', String(err?.message || err));
        continue;
      }

      if (bitmap.width > 6000 || bitmap.height > 6000) {
        try { bitmap.close?.(); } catch { /* noop */ }
        postError(correlationId, image_id, 'image.too_large', 'image exceeds 6000px on a side');
        continue;
      }

      try {
        const dataUrl = await previewOneImage(bitmap, paletteEntries, delta_e_threshold);
        const durationMs = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - start;

        // If the controller was aborted while we processed, drop result.
        if (controller.signal.aborted) {
          return;
        }
        // If a newer correlationId took over for this image, drop result.
        const cur = activeByImageId.get(image_id);
        if (cur && cur.correlationId !== correlationId) {
          continue;
        }

         
        self.postMessage({
          type: 'PREVIEW_RESULT',
          correlationId,
          image_id,
          data_url: dataUrl,
          durationMs,
        });
      } catch (err) {
        postError(correlationId, image_id, 'worker.internal', String(err?.message || err));
      } finally {
        try { bitmap.close?.(); } catch { /* noop */ }
      }
    }
  } finally {
    controllerByCorrelation.delete(correlationId);
    for (const [k, v] of activeByImageId) {
      if (v.correlationId === correlationId) activeByImageId.delete(k);
    }
  }
}

async function previewOneImage(bitmap, paletteEntries, deltaEThreshold) {
  const w = bitmap.width;
  const h = bitmap.height;
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0);
  const imageData = ctx.getImageData(0, 0, w, h);
  const data = imageData.data;

  // Collect opaque samples on a 1/4 stride (every 2 px on each axis).
  const samples = [];
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      const idx = (y * w + x) * 4;
      if (data[idx + 3] >= 32) {
        samples.push([data[idx], data[idx + 1], data[idx + 2]]);
      }
    }
  }

  // If no opaque pixels, no swap to perform — emit unchanged image.
  if (samples.length === 0) {
    ctx.putImageData(imageData, 0, 0);
    return canvasToDataUrl(canvas);
  }

  // Tiny RGB-space K-means with K up to 6.
  const K = Math.min(6, samples.length);
  const centroids = pickInitialCentroids(samples, K);
  for (let iter = 0; iter < 6; iter++) {
    const groups = Array.from({ length: K }, () => [0, 0, 0, 0]); // r,g,b,count
    for (const s of samples) {
      let best = 0;
      let bestD = Infinity;
      for (let k = 0; k < K; k++) {
        const c = centroids[k];
        const dr = s[0] - c[0];
        const dg = s[1] - c[1];
        const db = s[2] - c[2];
        const d = dr * dr + dg * dg + db * db;
        if (d < bestD) {
          bestD = d;
          best = k;
        }
      }
      const grp = groups[best];
      grp[0] += s[0];
      grp[1] += s[1];
      grp[2] += s[2];
      grp[3] += 1;
    }
    for (let k = 0; k < K; k++) {
      const grp = groups[k];
      if (grp[3] > 0) {
        centroids[k] = [grp[0] / grp[3], grp[1] / grp[3], grp[2] / grp[3]];
      }
    }
  }

  // For each cluster centroid: compute LAB and find nearest palette entry.
  const mapping = new Array(K).fill(null);
  for (let k = 0; k < K; k++) {
    const cLab = rgbToLab(centroids[k]);
    let best = null;
    let bestD = Infinity;
    for (const entry of paletteEntries) {
      const d = deltaE2000(cLab, entry.source_lab);
      if (d < bestD) {
        bestD = d;
        best = entry;
      }
    }
    if (best && bestD < deltaEThreshold) {
      mapping[k] = best.target_rgb;
    }
  }

  // Apply mapping per opaque pixel; nearest-cluster (RGB) classification.
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const idx = (y * w + x) * 4;
      if (data[idx + 3] < 32) continue;
      let best = 0;
      let bestD = Infinity;
      for (let k = 0; k < K; k++) {
        const c = centroids[k];
        const dr = data[idx] - c[0];
        const dg = data[idx + 1] - c[1];
        const db = data[idx + 2] - c[2];
        const d = dr * dr + dg * dg + db * db;
        if (d < bestD) {
          bestD = d;
          best = k;
        }
      }
      const target = mapping[best];
      if (target) {
        data[idx] = target[0];
        data[idx + 1] = target[1];
        data[idx + 2] = target[2];
        // alpha (data[idx+3]) preserved
      }
    }
  }

  ctx.putImageData(imageData, 0, 0);
  return canvasToDataUrl(canvas);
}

function pickInitialCentroids(samples, K) {
  // Spread initial centroids across the sample sequence (deterministic K-means++ light).
  const out = [];
  if (samples.length === 0) return out;
  const stride = Math.max(1, Math.floor(samples.length / K));
  for (let k = 0; k < K; k++) {
    const idx = Math.min(samples.length - 1, k * stride);
    const s = samples[idx];
    out.push([s[0], s[1], s[2]]);
  }
  return out;
}

async function canvasToDataUrl(canvas) {
  const blob = await canvas.convertToBlob({ type: 'image/png' });
  // FileReader is available inside DedicatedWorkerGlobalScope; fall back to ArrayBuffer base64 if not.
  if (typeof FileReader !== 'undefined') {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result || '');
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }
  const buf = await blob.arrayBuffer();
  let binary = '';
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
   
  const b64 = (typeof self !== 'undefined' && self.btoa) ? self.btoa(binary) : '';
  return `data:image/png;base64,${b64}`;
}

function handleCancel(message) {
  const { correlationId } = message || {};
  const ctrl = controllerByCorrelation.get(correlationId);
  if (ctrl) {
    ctrl.abort();
    controllerByCorrelation.delete(correlationId);
  }
}

// Attach onmessage on the worker scope. In a jsdom test env `self` is
// globalThis; this still wires up so the import is side-effect-safe but doesn't
// throw at import time.
if (typeof self !== 'undefined') {
   
  self.onmessage = (e) => {
    try {
      const data = e?.data || {};
      if (data.type === 'PREVIEW_REQUEST') {
        // Run async; errors handled inside.
        handlePreviewRequest(data).catch((err) => {
          postError(
            data.correlationId,
            null,
            'worker.internal',
            String(err?.message || err),
          );
        });
      } else if (data.type === 'CANCEL') {
        handleCancel(data);
      }
    } catch (err) {
      postError(
        e?.data?.correlationId || null,
        null,
        'worker.internal',
        String(err?.message || err),
      );
    }
  };
}
