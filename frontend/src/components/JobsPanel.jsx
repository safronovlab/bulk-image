import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  X, Download, Trash2, RefreshCw, Loader2, CheckCircle2, AlertOctagon,
  Clock, Activity, FileArchive, History, Hash, Layers, Image as ImageIcon,
  Undo2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../api';

/* ── Helpers ─────────────────────────────────────────────────────────────── */

const TERMINAL = new Set(['completed', 'failed', 'done', 'error']);
const ACTIVE   = new Set(['pending', 'processing', 'running', 'queued']);

const isTerminal = (s) => TERMINAL.has((s || '').toLowerCase());
const isActive   = (s) => ACTIVE.has((s || '').toLowerCase());

/* Status → semantic palette token. We map every backend variant to one of
   four buckets so the panel stays glanceable even if the backend renames. */
const STATUS_THEME = {
  completed: { dot: 'var(--color-ok)',   text: 'var(--color-ok)',   bg: 'var(--color-ok-bg)',   icon: CheckCircle2,  label: 'Done' },
  done:      { dot: 'var(--color-ok)',   text: 'var(--color-ok)',   bg: 'var(--color-ok-bg)',   icon: CheckCircle2,  label: 'Done' },
  failed:    { dot: 'var(--color-bad)',  text: 'var(--color-bad)',  bg: 'var(--color-bad-bg)',  icon: AlertOctagon,  label: 'Failed' },
  error:     { dot: 'var(--color-bad)',  text: 'var(--color-bad)',  bg: 'var(--color-bad-bg)',  icon: AlertOctagon,  label: 'Failed' },
  processing:{ dot: 'var(--color-clay)', text: 'var(--color-clay-deep)', bg: 'var(--color-clay-tint)', icon: Activity, label: 'Running' },
  running:   { dot: 'var(--color-clay)', text: 'var(--color-clay-deep)', bg: 'var(--color-clay-tint)', icon: Activity, label: 'Running' },
  pending:   { dot: 'var(--color-warn)', text: 'var(--color-warn)', bg: 'var(--color-warn-bg)', icon: Clock,         label: 'Pending' },
  queued:    { dot: 'var(--color-warn)', text: 'var(--color-warn)', bg: 'var(--color-warn-bg)', icon: Clock,         label: 'Queued' },
};

const themeFor = (status) =>
  STATUS_THEME[(status || '').toLowerCase()] ||
  { dot: 'var(--color-ink-3)', text: 'var(--color-ink-3)', bg: 'var(--color-paper-3)', icon: Clock, label: status || 'Unknown' };

/* Relative-time formatter — "12s ago", "4m ago", "3h ago", "2d ago". */
const relativeTime = (iso) => {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diff = Math.max(0, Date.now() - t);
  const s = Math.floor(diff / 1000);
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.floor(d / 30);
  return `${mo}mo ago`;
};

const shortId = (id) => {
  if (!id) return '—';
  const s = String(id);
  return s.length > 10 ? `${s.slice(0, 4)}…${s.slice(-4)}` : s;
};

/* ── Job Row ─────────────────────────────────────────────────────────────── */

function JobRow({ job, onDownload, onDelete, downloading, deletingId }) {
  const status = (job.status || '').toLowerCase();
  const theme = themeFor(status);
  const Icon = theme.icon;

  // Compute progress — backend sometimes omits it for terminal/pending states.
  const progress =
    typeof job.progress === 'number'
      ? Math.max(0, Math.min(100, job.progress))
      : isTerminal(status) ? 100 : 0;

  // Inline confirm-delete state — single "Confirm" button replaces "Delete"
  // for ~3s. Avoids modal noise and matches the editorial restraint of the rest.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const confirmTimer = useRef(null);

  useEffect(() => () => { if (confirmTimer.current) clearTimeout(confirmTimer.current); }, []);

  const armDelete = () => {
    setConfirmingDelete(true);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    confirmTimer.current = setTimeout(() => setConfirmingDelete(false), 3000);
  };
  const fireDelete = () => {
    setConfirmingDelete(false);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    onDelete(job.job_id);
  };
  const cancelDelete = () => {
    setConfirmingDelete(false);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
  };

  const isDownloading = downloading === job.job_id;
  const isDeleting = deletingId === job.job_id;

  // Counts — total_tasks / total_variations / total_images vary by backend version.
  const designCount =
    job.total_tasks ?? job.image_count ?? job.total_images ?? job.images?.length ?? null;
  const variationCount = job.total_variations ?? job.variation_count ?? null;

  return (
    <article
      className={`group bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-xl overflow-hidden transition-colors ${
        isActive(status) ? 'hover:border-[var(--color-clay)]/40' : 'hover:border-[var(--color-rule-strong)]'
      }`}
    >
      {/* Top row — id, time, status pill */}
      <div className="flex items-center gap-3 px-3.5 pt-3 pb-2">
        <span
          aria-hidden
          className={`w-2 h-2 rounded-full shrink-0 ${isActive(status) ? 'animate-pulse-soft' : ''}`}
          style={{ backgroundColor: theme.dot }}
        />
        <div className="flex items-baseline gap-2 min-w-0 flex-1">
          <span className="font-mono text-[12px] font-semibold text-[var(--color-ink)] tracking-tight tabular-nums">
            {shortId(job.job_id)}
          </span>
          <span className="text-[10px] font-mono text-[var(--color-ink-3)] tabular-nums truncate">
            {relativeTime(job.created_at || job.created || job.createdAt)}
          </span>
        </div>
        <span
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-[0.12em] font-semibold shrink-0"
          style={{ backgroundColor: theme.bg, color: theme.text }}
        >
          <Icon className={`w-3 h-3 ${isActive(status) ? 'animate-spin' : ''}`} strokeWidth={2.5} />
          {theme.label}
        </span>
      </div>

      {/* Meta row — design count + variation count */}
      <div className="px-3.5 pb-2 flex items-center gap-3 text-[11px] font-mono text-[var(--color-ink-3)] tabular-nums">
        {designCount != null && (
          <span className="flex items-center gap-1">
            <ImageIcon className="w-3 h-3" />
            {designCount} design{designCount !== 1 ? 's' : ''}
          </span>
        )}
        {variationCount != null && (
          <>
            <span className="text-[var(--color-ink-4)]">·</span>
            <span className="flex items-center gap-1">
              <Layers className="w-3 h-3" />
              {variationCount} var{variationCount !== 1 ? 's' : ''}
            </span>
          </>
        )}
        {job.job_id && (
          <span className="ml-auto flex items-center gap-1 text-[var(--color-ink-4)]">
            <Hash className="w-3 h-3" />
            <span className="truncate max-w-[120px]" title={job.job_id}>{job.job_id}</span>
          </span>
        )}
      </div>

      {/* Progress bar — only meaningful while running */}
      {isActive(status) && (
        <div className="px-3.5 pb-2.5">
          <div className="w-full h-[3px] bg-[var(--color-paper-3)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--color-clay)] rounded-full transition-all duration-700 animate-progress-stripe"
              style={{ width: `${progress}%`, backgroundImage: 'linear-gradient(45deg, rgba(255,255,255,0.20) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.20) 50%, rgba(255,255,255,0.20) 75%, transparent 75%)', backgroundSize: '0.6rem 0.6rem' }}
            />
          </div>
          <div className="flex items-center justify-between mt-1 text-[9px] font-mono uppercase tracking-wider tabular-nums text-[var(--color-ink-3)]">
            <span>processing</span>
            <span>{progress}%</span>
          </div>
        </div>
      )}

      {/* Failure detail */}
      {(status === 'failed' || status === 'error') && job.error && (
        <div className="mx-3.5 mb-2.5 bg-[var(--color-bad-bg)] border border-[var(--color-bad)]/25 rounded-md px-2.5 py-1.5">
          <p className="text-[11px] text-[var(--color-bad)] leading-snug break-words">
            <span className="font-mono uppercase tracking-wider text-[10px] mr-1.5">error</span>
            {job.error}
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-t border-[var(--color-rule)] bg-[var(--color-paper)]/50">
        {(status === 'completed' || status === 'done') && (
          <button
            onClick={() => onDownload(job.job_id)}
            disabled={isDownloading}
            className="btn-press flex items-center gap-1.5 px-2.5 py-1.5 bg-[var(--color-ink)] hover:bg-[#2B2B2B] text-[var(--color-paper)] rounded-md text-[11px] font-medium transition-colors disabled:opacity-40"
          >
            {isDownloading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
            ZIP
          </button>
        )}

        <span className="flex-1" />

        {confirmingDelete ? (
          <>
            <button
              onClick={cancelDelete}
              className="btn-press flex items-center gap-1 px-2 py-1.5 text-[var(--color-ink-3)] hover:text-[var(--color-ink)] rounded-md text-[10px] font-mono uppercase tracking-wider transition-colors"
              title="Cancel"
            >
              <Undo2 className="w-3 h-3" />
              cancel
            </button>
            <button
              onClick={fireDelete}
              autoFocus
              className="btn-press flex items-center gap-1.5 px-2.5 py-1.5 bg-[var(--color-bad)] hover:bg-[#8E3F29] text-[var(--color-paper)] rounded-md text-[11px] font-semibold transition-colors animate-fade-in"
            >
              <Trash2 className="w-3 h-3" />
              Confirm delete
            </button>
          </>
        ) : (
          <button
            onClick={armDelete}
            disabled={isDeleting}
            className="btn-press flex items-center justify-center w-7 h-7 rounded-md text-[var(--color-ink-4)] hover:text-[var(--color-bad)] hover:bg-[var(--color-bad-bg)] transition-colors disabled:opacity-40"
            title="Delete job"
            aria-label="Delete job"
          >
            {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
    </article>
  );
}

/* ── Panel ───────────────────────────────────────────────────────────────── */

export default function JobsPanel({ onClose }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  const fetchJobs = useCallback(async () => {
    // v2 spec has no list-jobs endpoint — frontend tracks history in
    // localStorage via api.recordJob() at submit time. Enrich each known
    // job_id with a fresh /api/jobs/{id} status fetch.
    try {
      const local = api.listLocalJobs();
      if (local.length === 0) {
        if (mountedRef.current) {
          setJobs([]);
          setError(null);
        }
        return;
      }
      const settled = await Promise.allSettled(
        local.map((meta) =>
          api
            .getJobStatus(meta.job_id)
            .then((status) => ({ ...meta, ...status }))
            .catch(() => meta)
        )
      );
      if (!mountedRef.current) return;
      const list = settled
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value);
      list.sort((a, b) => {
        const ta = new Date(a.created_at || a.recorded_at || 0).getTime();
        const tb = new Date(b.created_at || b.recorded_at || 0).getTime();
        return tb - ta;
      });
      setJobs(list);
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err.message || 'Failed to load jobs');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  /* Targeted poll — only re-fetch jobs that are still active. Avoids the
     full-list flash and keeps the bandwidth footprint tiny. */
  const pollActive = useCallback(async () => {
    const active = jobs.filter((j) => isActive(j.status));
    if (active.length === 0) return;
    try {
      const updates = await Promise.allSettled(
        active.map((j) => api.getJobStatus(j.job_id))
      );
      if (!mountedRef.current) return;
      const byId = {};
      updates.forEach((r, i) => {
        if (r.status === 'fulfilled') byId[active[i].job_id] = r.value;
      });
      setJobs((prev) => prev.map((j) => byId[j.job_id] ? { ...j, ...byId[j.job_id] } : j));
    } catch { /* swallow — next tick will retry */ }
  }, [jobs]);

  useEffect(() => {
    mountedRef.current = true;
    fetchJobs();
    return () => { mountedRef.current = false; };
  }, [fetchJobs]);

  /* Active-only polling — interval lives only while at least one job is
     pending/running. Re-evaluated whenever jobs change. */
  useEffect(() => {
    const hasActive = jobs.some((j) => isActive(j.status));
    if (!hasActive) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return undefined;
    }
    if (pollRef.current) return undefined;
    pollRef.current = setInterval(() => { pollActive(); }, 2000);
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [jobs, pollActive]);

  /* Esc closes the panel — slide-over standard. */
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  /* Lock body scroll while open */
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  const handleDownload = async (jobId) => {
    setDownloading(jobId);
    toast.loading('Preparing ZIP…', { id: `dl-${jobId}` });
    try {
      await api.downloadJob(jobId);
      toast.success('Download started', { id: `dl-${jobId}` });
    } catch (err) {
      toast.error(err.message || 'Download failed', { id: `dl-${jobId}` });
    } finally {
      setDownloading(null);
    }
  };

  const handleDelete = async (jobId) => {
    setDeletingId(jobId);
    try {
      await api.deleteJob(jobId);
      api.forgetLocalJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
      toast.success('Job deleted');
    } catch (err) {
      toast.error(err.message || 'Delete failed');
    } finally {
      setDeletingId(null);
    }
  };

  const stats = useMemo(() => {
    const active = jobs.filter((j) => isActive(j.status)).length;
    const done = jobs.filter((j) => {
      const s = (j.status || '').toLowerCase();
      return s === 'completed' || s === 'done';
    }).length;
    const failed = jobs.filter((j) => {
      const s = (j.status || '').toLowerCase();
      return s === 'failed' || s === 'error';
    }).length;
    return { total: jobs.length, active, done, failed };
  }, [jobs]);

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Jobs panel">
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close jobs panel"
        onClick={onClose}
        className="absolute inset-0 bg-[#1A1A1A]/30 backdrop-blur-sm animate-fade-in cursor-default"
      />

      {/* Panel */}
      <aside
        className="ml-auto relative h-full w-full sm:w-[440px] lg:w-[480px] bg-[var(--color-paper)] border-l border-[var(--color-rule)] flex flex-col shadow-2xl"
        style={{ animation: 'slideInRight 0.32s cubic-bezier(0.22, 0.61, 0.36, 1) both' }}
      >
        <style>{`
          @keyframes slideInRight {
            from { transform: translateX(24px); opacity: 0.6; }
            to   { transform: translateX(0);    opacity: 1; }
          }
        `}</style>

        {/* Header */}
        <header className="px-5 pt-5 pb-3 border-b border-[var(--color-rule)] bg-[var(--color-paper)]/85 backdrop-blur-md sticky top-0 z-10">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-ink-3)] mb-1">
                History
              </p>
              <h2 className="font-display text-[22px] leading-tight text-[var(--color-ink)] tracking-tight flex items-center gap-2">
                <History className="w-4 h-4 text-[var(--color-clay-deep)]" />
                Jobs
              </h2>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={fetchJobs}
                disabled={loading}
                className="btn-press w-8 h-8 flex items-center justify-center rounded-md text-[var(--color-ink-3)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-3)] transition-colors disabled:opacity-40"
                title="Refresh"
                aria-label="Refresh jobs"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="btn-press w-8 h-8 flex items-center justify-center rounded-md text-[var(--color-ink-3)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-3)] transition-colors"
                title="Close (Esc)"
                aria-label="Close panel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Stat strip */}
          {jobs.length > 0 && (
            <div className="mt-3 grid grid-cols-4 gap-2">
              <StatCell label="Total"   value={stats.total}  />
              <StatCell label="Running" value={stats.active} accent={stats.active > 0} />
              <StatCell label="Done"    value={stats.done}   tone="ok"  />
              <StatCell label="Failed"  value={stats.failed} tone="bad" />
            </div>
          )}
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2.5">
          {loading && jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2.5 animate-fade-in">
              <Loader2 className="w-5 h-5 text-[var(--color-clay-deep)] animate-spin" />
              <p className="text-[12px] font-mono text-[var(--color-ink-3)] uppercase tracking-wider">loading jobs</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center animate-fade-in">
              <div className="w-11 h-11 rounded-xl bg-[var(--color-bad-bg)] border border-[var(--color-bad)]/25 flex items-center justify-center">
                <AlertOctagon className="w-5 h-5 text-[var(--color-bad)]" />
              </div>
              <div>
                <p className="text-[13px] text-[var(--color-ink)] font-medium">Couldn't load jobs</p>
                <p className="text-[11px] font-mono text-[var(--color-ink-3)] mt-1 max-w-[28ch] mx-auto">
                  {error}
                </p>
              </div>
              <button
                onClick={fetchJobs}
                className="btn-press flex items-center gap-1.5 mt-1 px-3 py-1.5 bg-[var(--color-ink)] hover:bg-[#2B2B2B] text-[var(--color-paper)] rounded-md text-[12px] font-medium transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Retry
              </button>
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center animate-fade-in">
              <div className="w-12 h-12 rounded-xl bg-[var(--color-paper-3)] border border-[var(--color-rule)] flex items-center justify-center">
                <FileArchive className="w-5 h-5 text-[var(--color-ink-3)]" />
              </div>
              <div>
                <p className="font-display text-[16px] text-[var(--color-ink)] leading-tight">
                  No jobs yet
                </p>
                <p className="text-[12px] text-[var(--color-ink-2)] mt-1.5 max-w-[32ch] mx-auto leading-relaxed">
                  Process some images from the <span className="font-medium text-[var(--color-ink)]">Batch</span> tab and they'll show up here.
                </p>
              </div>
            </div>
          ) : (
            <div className="stagger-children">
              {jobs.map((job) => (
                <JobRow
                  key={job.job_id}
                  job={job}
                  onDownload={handleDownload}
                  onDelete={handleDelete}
                  downloading={downloading}
                  deletingId={deletingId}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer — telemetry strip */}
        <footer className="border-t border-[var(--color-rule)] px-5 py-2.5 bg-[var(--color-paper-2)]">
          <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-[var(--color-ink-3)] flex items-center gap-2">
            {stats.active > 0 ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-clay)] animate-pulse-soft" />
                Polling · refreshes every 2s
              </>
            ) : (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-rule-strong)]" />
                Idle · no active jobs
              </>
            )}
          </p>
        </footer>
      </aside>
    </div>
  );
}

/* ── Tiny presentational atoms ───────────────────────────────────────────── */

function StatCell({ label, value, tone, accent }) {
  const color =
    tone === 'ok'  ? 'var(--color-ok)'
  : tone === 'bad' ? 'var(--color-bad)'
  : accent         ? 'var(--color-clay-deep)'
  :                  'var(--color-ink)';
  return (
    <div className="bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-md px-2 py-1.5">
      <p className="text-[9px] font-mono uppercase tracking-[0.14em] text-[var(--color-ink-3)] leading-none">
        {label}
      </p>
      <p
        className="font-mono text-[15px] font-semibold tabular-nums leading-tight mt-1"
        style={{ color }}
      >
        {value}
      </p>
    </div>
  );
}
