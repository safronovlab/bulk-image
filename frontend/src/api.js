/**
 * api.js — unified API client for the Bulk Recolor v2 frontend.
 *
 * Surface mirrors the master spec
 * after the spec contract; v2 components and v1-era components both import
 * from this module via `import { api } from '../api'`.
 *
 * v1-only methods (uploadImages plural, batchAnalyze, pickColor, presets,
 * suggestMappings, previewReplace, getImages list endpoint) have been
 * removed — the backend no longer exposes them. See AUDIT_REPORT.md §6.
 */

const TOKEN_KEY = 'auth_token';

const getToken = () => localStorage.getItem(TOKEN_KEY);

const handleResponse = async (res) => {
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const envelope = data?.error?.message || data?.detail || `Error ${res.status}`;
    throw new Error(envelope);
  }
  return res;
};

const headers = () => ({ Authorization: `Bearer ${getToken()}` });

const jsonHeaders = () => ({
  ...headers(),
  'Content-Type': 'application/json',
});

const previewUrl = (imageId) => {
  const tok = getToken();
  return tok
    ? `/api/images/${imageId}/preview?t=${encodeURIComponent(tok)}`
    : `/api/images/${imageId}/preview`;
};

export const api = {
  // ── Auth ──────────────────────────────────────────────────────────
  async login(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    await handleResponse(res);
    return res.json();
  },

  async logout() {
    const res = await fetch('/api/auth/logout', {
      method: 'POST',
      headers: headers(),
    });
    await handleResponse(res);
    return res.json();
  },

  // ── Images (POST /upload, GET /clusters, /preview, POST /click-fix, DELETE) ──
  async uploadImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/images/upload', {
      method: 'POST',
      headers: headers(),
      body: formData,
    });
    await handleResponse(res);
    return res.json();
  },

  async getImageClusters(imageId) {
    const res = await fetch(`/api/images/${imageId}/clusters`, {
      headers: headers(),
    });
    await handleResponse(res);
    return res.json();
  },
  // v2 alias used by ColorStudioTab per spec.
  getClusters(imageId) {
    return this.getImageClusters(imageId);
  },

  getPreviewUrl: previewUrl,
  getImagePreviewUrl: previewUrl,

  async clickFix(imageId, { click_x, click_y, target_rgb }) {
    const res = await fetch(`/api/images/${imageId}/click-fix`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ click_x, click_y, target_rgb }),
    });
    await handleResponse(res);
    return res.json();
  },

  // POST /api/images/{image_id}/click-fix/preview — returns mask PNG as a
  // blob URL. Caller is responsible for revokeObjectURL when no longer
  // needed (we revoke at confirm/cancel time in ClickFixCanvas).
  async clickFixPreview(imageId, { click_x, click_y }) {
    const res = await fetch(`/api/images/${imageId}/click-fix/preview`, {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ click_x, click_y }),
    });
    await handleResponse(res);
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },

  async deleteImage(imageId) {
    const res = await fetch(`/api/images/${imageId}`, {
      method: 'DELETE',
      headers: headers(),
    });
    await handleResponse(res);
    return res.json();
  },

  // ── Palette ───────────────────────────────────────────────────────
  async createPalette({ label, entries }) {
    const res = await fetch('/api/palettes', {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ label, entries }),
    });
    await handleResponse(res);
    return res.json();
  },

  async getCurrentPalette() {
    const res = await fetch('/api/palettes/current', { headers: headers() });
    await handleResponse(res);
    return res.json();
  },

  // ── Jobs ──────────────────────────────────────────────────────────
  async startRecolorJob({ image_ids, palette_id }) {
    const res = await fetch('/api/jobs/recolor', {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ image_ids, palette_id }),
    });
    await handleResponse(res);
    return res.json();
  },
  // v2 alias used by BatchProcessTab per spec.
  submitRecolorJob(payload) {
    return this.startRecolorJob(payload);
  },

  async getJobStatus(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`, { headers: headers() });
    await handleResponse(res);
    return res.json();
  },

  async downloadJobZip(jobId) {
    const res = await fetch(`/api/jobs/${jobId}/download`, { headers: headers() });
    await handleResponse(res);
    return res.blob();
  },

  // Convenience: triggers a browser download of the result ZIP.
  async downloadJob(jobId, filename) {
    const blob = await this.downloadJobZip(jobId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `${jobId}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  async deleteJob(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`, {
      method: 'DELETE',
      headers: headers(),
    });
    await handleResponse(res);
    return res.json();
  },

  // ── Local job-history helpers (v2 has no list endpoint by spec) ───
  // Frontend tracks job_ids in localStorage; JobsPanel iterates.
  recordJob(jobId, meta = {}) {
    const list = this.listLocalJobs();
    if (list.find((j) => j.job_id === jobId)) return;
    list.unshift({ job_id: jobId, ...meta, recorded_at: new Date().toISOString() });
    localStorage.setItem('job_history', JSON.stringify(list.slice(0, 50)));
  },

  listLocalJobs() {
    try {
      return JSON.parse(localStorage.getItem('job_history') || '[]');
    } catch {
      return [];
    }
  },

  forgetLocalJob(jobId) {
    const list = this.listLocalJobs().filter((j) => j.job_id !== jobId);
    localStorage.setItem('job_history', JSON.stringify(list));
  },
};
