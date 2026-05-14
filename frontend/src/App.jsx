import { useState, useEffect, lazy, Suspense } from 'react';
import { Toaster } from 'react-hot-toast';
import {
  UploadCloud, Pipette, Layers, LogOut, Menu, X, ChevronRight,
  HelpCircle, Loader2, History, Eye, Workflow, Sparkles,
} from 'lucide-react';
import LoginPage from './components/LoginPage';
import UploadTab from './components/UploadTab';
import toast from 'react-hot-toast';
import { api } from './api';
import { toastOptions } from './ui/toast';

// Code-split heavy tabs.
const ColorStudioTab  = lazy(() => import('./components/ColorStudioTab'));
const BatchProcessTab = lazy(() => import('./components/BatchProcessTab'));
const JobsPanel       = lazy(() => import('./components/JobsPanel'));

const tabPreloaders = {
  studio:  () => import('./components/ColorStudioTab'),
  batch:   () => import('./components/BatchProcessTab'),
};

const TabFallback = () => (
  <div className="flex items-center justify-center py-20">
    <Loader2 className="w-4 h-4 text-[var(--color-ink-3)] animate-spin" />
  </div>
);

const TABS = [
  { id: 'upload',  label: 'Upload',  icon: UploadCloud, hint: 'PNG · JPEG · drag & drop' },
  { id: 'studio',  label: 'Studio',  icon: Pipette,     hint: 'Pick & map colors per design' },
  { id: 'batch',   label: 'Batch',   icon: Layers,      hint: 'Variations & job submission' },
];

const ONBOARDING_STEPS = [
  {
    title: 'Upload your designs',
    description: 'Drop in PNG or JPEG files. They are preserved exactly — DPI, resolution and quality untouched.',
    Icon: UploadCloud,
  },
  {
    title: 'Pick & map colors',
    description: 'Use the eyedropper or top-color chips to choose a source. Set the target hex you want it replaced with.',
    Icon: Pipette,
  },
  {
    title: 'Preview, refine, batch-apply',
    description: 'See before/after instantly. Adjust tolerance per design or apply your settings to the whole set.',
    Icon: Eye,
  },
  {
    title: 'Process & download',
    description: 'Submit a job, watch the progress, download the print-ready ZIP. The Jobs panel keeps history.',
    Icon: Sparkles,
  },
];

export default function App() {
  const [authenticated, setAuthenticated] = useState(!!localStorage.getItem('auth_token'));
  const [activeTab, setActiveTab] = useState('upload');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [jobsPanelOpen, setJobsPanelOpen] = useState(false);

  const [images, setImages] = useState([]);
  const [dominantColors, setDominantColors] = useState({});
  const [studioSelectedImageId, setStudioSelectedImageId] = useState(null);

  // ── v2 wiring (master spec
  const [currentPalette, setCurrentPalette] = useState(null);
  // Save replaces the draft with a server-issued palette (carries palette_id
  // for batch jobs). Click-fix only needs target_hex, so the draft is enough.
  const handlePaletteCreated = (palette) => setCurrentPalette(palette);
  const handlePaletteChange = (draft) => {
    setCurrentPalette((prev) => ({
      // Preserve palette_id from the last saved version if present, so a
      // batch can still be submitted with this palette without re-saving.
      palette_id: prev?.palette_id,
      ...draft,
    }));
  };
  const handleResultImageReplaced = (newId, prevId) => {
    // Click-fix returns a new image_id pointing at the recolored result.
    // Swap the id in the gallery so re-renders and re-fetches keep working.
    // No Jobs panel open (this is a synchronous recolor, not a batch job).
    // Toast lives in ColorStudioTab.handleFixSubmitted.
    setStudioSelectedImageId(newId);
    setImages((prev) => {
      const oldRec = prev.find((i) => i.image_id === prevId);
      if (!oldRec) return prev;
      const newRec = { ...oldRec, image_id: newId, parent_image_id: prevId };
      return prev.map((i) => (i.image_id === prevId ? newRec : i));
    });
  };
  const handleJobSubmitted = (result) => {
    if (result?.job_id) {
      api.recordJob(result.job_id, {
        palette_id: currentPalette?.palette_id,
        palette_label: currentPalette?.label,
        image_count: images.length,
      });
    }
    setJobsPanelOpen(true);
  };

  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingStep, setOnboardingStep] = useState(0);

  useEffect(() => {
    if (authenticated) {
      const seen = localStorage.getItem('onboarding_seen');
      if (!seen) setTimeout(() => setShowOnboarding(true), 600);
    }
  }, [authenticated]);

  // Auto-select first uploaded design for the Studio tab when none is picked.
  useEffect(() => {
    if (!studioSelectedImageId && images.length > 0) {
      setStudioSelectedImageId(images[0].image_id);
    }
    if (studioSelectedImageId && !images.find((i) => i.image_id === studioSelectedImageId)) {
      setStudioSelectedImageId(images[0]?.image_id || null);
    }
  }, [images, studioSelectedImageId]);

  const handleLogout = async () => {
    try { await api.logout(); } catch { /* continue */ }
    localStorage.removeItem('auth_token');
    setAuthenticated(false);
    setImages([]);
    setDominantColors({});
    toast.success('Signed out');
  };

  const dismissOnboarding = () => {
    setShowOnboarding(false);
    localStorage.setItem('onboarding_seen', 'true');
  };
  const nextOnboardingStep = () => {
    if (onboardingStep < ONBOARDING_STEPS.length - 1) setOnboardingStep((s) => s + 1);
    else dismissOnboarding();
  };

  if (!authenticated) {
    return (
      <>
        <Toaster position="top-right" toastOptions={toastOptions} />
        <LoginPage onLogin={() => setAuthenticated(true)} />
      </>
    );
  }

  const StepIcon = ONBOARDING_STEPS[onboardingStep].Icon;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-paper)]">
      <Toaster position="top-right" toastOptions={toastOptions} />

      {/* ── Onboarding ─────────────────────────────────────────────────── */}
      {showOnboarding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1A1A1A]/30 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-[var(--color-paper-2)] border border-[var(--color-rule)] rounded-2xl p-8 max-w-md w-full shadow-2xl animate-scale-in">
            <div className="space-y-5">
              <div className="flex items-start justify-between">
                <div className="w-11 h-11 rounded-xl bg-[var(--color-clay-tint)] border border-[var(--color-clay-soft)] flex items-center justify-center">
                  <StepIcon className="w-5 h-5 text-[var(--color-clay-deep)]" />
                </div>
                <span className="font-mono text-[10px] tracking-wider uppercase text-[var(--color-ink-3)]">
                  {String(onboardingStep + 1).padStart(2, '0')} / {String(ONBOARDING_STEPS.length).padStart(2, '0')}
                </span>
              </div>

              <div>
                <h2 className="font-display text-2xl text-[var(--color-ink)] leading-tight">
                  {ONBOARDING_STEPS[onboardingStep].title}
                </h2>
                <p className="text-[var(--color-ink-2)] text-[13px] leading-relaxed mt-2">
                  {ONBOARDING_STEPS[onboardingStep].description}
                </p>
              </div>

              <div className="flex gap-1">
                {ONBOARDING_STEPS.map((_, i) => (
                  <div
                    key={i}
                    className={`h-[3px] flex-1 rounded-full transition-all duration-300 ${
                      i === onboardingStep
                        ? 'bg-[var(--color-clay)]'
                        : i < onboardingStep
                          ? 'bg-[var(--color-ink-3)]'
                          : 'bg-[var(--color-rule)]'
                    }`}
                  />
                ))}
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  onClick={dismissOnboarding}
                  className="btn-press flex-1 py-2.5 text-[13px] text-[var(--color-ink-2)] hover:text-[var(--color-ink)] border border-[var(--color-rule)] hover:border-[var(--color-rule-strong)] rounded-lg transition-colors"
                >
                  Skip
                </button>
                <button
                  onClick={nextOnboardingStep}
                  className="btn-press flex-1 py-2.5 text-[13px] font-semibold bg-[var(--color-ink)] hover:bg-[#2B2B2B] text-[var(--color-paper)] rounded-lg transition-colors flex items-center justify-center gap-1"
                >
                  {onboardingStep < ONBOARDING_STEPS.length - 1 ? (
                    <>Next <ChevronRight className="w-4 h-4" /></>
                  ) : (
                    'Get started'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Top nav ────────────────────────────────────────────────────── */}
      <nav className="bg-[var(--color-paper)]/85 backdrop-blur-md border-b border-[var(--color-rule)] sticky top-0 z-40">
        <div className="max-w-[1280px] mx-auto px-5">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-md bg-[var(--color-ink)] flex items-center justify-center">
                <Pipette className="w-3.5 h-3.5 text-[var(--color-paper)]" />
              </div>
              <span className="font-display text-[17px] font-semibold tracking-tight text-[var(--color-ink)] hidden sm:block">
                Color Studio
              </span>
            </div>

            {/* Desktop tabs — pill-less, underline-on-active, editorial */}
            <div className="hidden md:flex items-center gap-1">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    onMouseEnter={() => tabPreloaders[tab.id]?.()}
                    onFocus={() => tabPreloaders[tab.id]?.()}
                    className={`relative flex items-center gap-2 px-3.5 h-14 text-[13px] font-medium transition-colors ${
                      active
                        ? 'text-[var(--color-ink)]'
                        : 'text-[var(--color-ink-3)] hover:text-[var(--color-ink-2)]'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${active ? 'text-[var(--color-clay-deep)]' : ''}`} />
                    {tab.label}
                    <span
                      className={`absolute left-3 right-3 -bottom-px h-[2px] rounded-full transition-all ${
                        active ? 'bg-[var(--color-clay-deep)]' : 'bg-transparent'
                      }`}
                    />
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => setJobsPanelOpen(true)}
                className="hidden sm:flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[12px] font-medium text-[var(--color-ink-2)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-3)] transition-colors"
                title="Jobs history"
              >
                <History className="w-3.5 h-3.5" />
                Jobs
              </button>
              <button
                onClick={() => { setShowOnboarding(true); setOnboardingStep(0); }}
                className="w-8 h-8 flex items-center justify-center rounded-md text-[var(--color-ink-3)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-3)] transition-colors"
                title="Quick guide"
              >
                <HelpCircle className="w-4 h-4" />
              </button>
              <button
                onClick={handleLogout}
                className="btn-press flex items-center gap-1.5 h-8 px-2.5 text-[12px] font-medium text-[var(--color-ink-3)] hover:text-[var(--color-bad)] rounded-md hover:bg-[var(--color-bad-bg)] transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:block">Sign out</span>
              </button>

              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden w-8 h-8 flex items-center justify-center rounded-md bg-[var(--color-paper-3)] hover:bg-[var(--color-paper-4)] transition-colors"
              >
                {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {mobileMenuOpen && (
            <div className="md:hidden pb-3 space-y-1 animate-fade-in-down">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => { setActiveTab(tab.id); setMobileMenuOpen(false); }}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-[13px] font-medium transition-colors ${
                      active
                        ? 'bg-[var(--color-paper-3)] text-[var(--color-ink)]'
                        : 'text-[var(--color-ink-2)] hover:bg-[var(--color-paper-3)]'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${active ? 'text-[var(--color-clay-deep)]' : ''}`} />
                    <div className="text-left">
                      <div>{tab.label}</div>
                      <div className="text-[10px] text-[var(--color-ink-3)] font-mono">{tab.hint}</div>
                    </div>
                  </button>
                );
              })}
              <button
                onClick={() => { setJobsPanelOpen(true); setMobileMenuOpen(false); }}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-[13px] font-medium text-[var(--color-ink-2)] hover:bg-[var(--color-paper-3)] transition-colors"
              >
                <History className="w-4 h-4" />
                <div className="text-left">
                  <div>Jobs</div>
                  <div className="text-[10px] text-[var(--color-ink-3)] font-mono">history & downloads</div>
                </div>
              </button>
            </div>
          )}
        </div>
      </nav>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <main className="flex-1 max-w-[1280px] mx-auto w-full px-5 py-7 animate-fade-in-up">
        {activeTab === 'upload' && (
          <UploadTab
            images={images}
            setImages={setImages}
            dominantColors={dominantColors}
            setDominantColors={setDominantColors}
          />
        )}
        <Suspense fallback={<TabFallback />}>
          {activeTab === 'studio' && (
            <ColorStudioTab
              selectedImageId={studioSelectedImageId}
              setSelectedImageId={setStudioSelectedImageId}
              uploadedImages={images}
              currentPalette={currentPalette}
              onPaletteCreated={handlePaletteCreated}
              onPaletteChange={handlePaletteChange}
              onResultImageReplaced={handleResultImageReplaced}
            />
          )}
          {activeTab === 'batch' && (
            <BatchProcessTab
              uploadedImages={images}
              currentPalette={currentPalette}
              onPaletteCreated={handlePaletteCreated}
              onPaletteChange={handlePaletteChange}
              onJobSubmitted={handleJobSubmitted}
            />
          )}
        </Suspense>
      </main>

      {/* ── Jobs slide-over ────────────────────────────────────────────── */}
      <Suspense fallback={null}>
        {jobsPanelOpen && <JobsPanel onClose={() => setJobsPanelOpen(false)} />}
      </Suspense>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-[var(--color-rule)] py-3 text-center bg-[var(--color-paper)]">
        <p className="text-[10px] font-mono tracking-wider uppercase text-[var(--color-ink-3)]">
          <Workflow className="inline w-3 h-3 -mt-0.5 mr-1.5" />
          Bulk recolor · Server-side processing · Print-ready output
        </p>
      </footer>
    </div>
  );
}
