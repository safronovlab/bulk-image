import { useState } from 'react';
import { Lock, User, Loader2, Pipette, ArrowRight, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../api';

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      toast.error('Enter username and password');
      return;
    }
    setLoading(true);
    try {
      const data = await api.login(username, password);
      localStorage.setItem('auth_token', data.token);
      toast.success('Welcome back');
      onLogin();
    } catch (err) {
      toast.error(err.message || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-paper)] flex flex-col">
      {/* Faint paper-grain pattern, restrained */}
      <div
        aria-hidden
        className="fixed inset-0 pointer-events-none opacity-[0.35]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 20% 25%, rgba(204,120,92,0.08) 0px, transparent 280px), radial-gradient(circle at 80% 70%, rgba(74,74,72,0.05) 0px, transparent 260px)',
        }}
      />

      <div className="flex-1 flex items-center justify-center p-5 relative">
        <div className="w-full max-w-[420px] animate-fade-in-up">
          {/* Lockup */}
          <div className="mb-9">
            <div className="flex items-center gap-2.5 mb-7">
              <div className="w-8 h-8 rounded-md bg-[var(--color-ink)] flex items-center justify-center">
                <Pipette className="w-4 h-4 text-[var(--color-paper)]" />
              </div>
              <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-3)]">
                Color Studio
              </span>
            </div>
            <h1 className="font-display text-[36px] leading-[1.05] text-[var(--color-ink)] tracking-tight">
              Sign in to your<br/>workspace.
            </h1>
            <p className="mt-3 text-[14px] leading-relaxed text-[var(--color-ink-2)] max-w-[34ch]">
              Bulk color replacement for print-ready designs — pixel-perfect, DPI-preserving, server-side.
            </p>
          </div>

          {/* Form */}
          <form
            onSubmit={handleSubmit}
            className="bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-2xl p-7 shadow-sm space-y-4"
          >
            <div>
              <label className="block text-[10px] font-mono font-semibold tracking-[0.14em] uppercase text-[var(--color-ink-3)] mb-1.5">
                Username
              </label>
              <div className="relative group">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-ink-3)] group-focus-within:text-[var(--color-clay-deep)] transition-colors" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="username"
                  className="w-full pl-10 pr-3 py-2.5 bg-[var(--color-paper)] border border-[var(--color-rule)] rounded-lg text-[var(--color-ink)] text-[14px] placeholder:text-[var(--color-ink-4)] focus:outline-none focus:ring-2 focus:ring-[rgba(204,120,92,0.18)] focus:border-[var(--color-clay)] focus:bg-[var(--color-paper-2)] transition-all"
                  autoFocus
                  autoComplete="username"
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-mono font-semibold tracking-[0.14em] uppercase text-[var(--color-ink-3)] mb-1.5">
                Password
              </label>
              <div className="relative group">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-ink-3)] group-focus-within:text-[var(--color-clay-deep)] transition-colors" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-3 py-2.5 bg-[var(--color-paper)] border border-[var(--color-rule)] rounded-lg text-[var(--color-ink)] text-[14px] placeholder:text-[var(--color-ink-4)] focus:outline-none focus:ring-2 focus:ring-[rgba(204,120,92,0.18)] focus:border-[var(--color-clay)] focus:bg-[var(--color-paper-2)] transition-all font-mono tracking-tight"
                  autoComplete="current-password"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-press w-full mt-2 py-2.5 px-4 bg-[var(--color-ink)] hover:bg-[#2B2B2B] text-[var(--color-paper)] font-semibold text-[13px] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Signing in
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-5 flex items-center gap-2 justify-center text-[var(--color-ink-3)]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <p className="text-[11px] font-mono tracking-wide">
              Single-user · session-based tokens
            </p>
          </div>
        </div>
      </div>

      <footer className="px-5 py-4 text-center border-t border-[var(--color-rule)]">
        <p className="text-[10px] font-mono tracking-wider uppercase text-[var(--color-ink-3)]">
          Color Studio · v1
        </p>
      </footer>
    </div>
  );
}
