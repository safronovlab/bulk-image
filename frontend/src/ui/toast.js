// Shared toast styling — paper surface, ink text, hairline border, no emojis
// anywhere. Components import this and pass it as Toaster's toastOptions.

export const toastOptions = {
  style: {
    background: '#FFFCF7',
    color: '#1A1A1A',
    border: '1px solid #E8E2D2',
    borderRadius: '10px',
    fontSize: '13px',
    fontFamily:
      "'Inter', ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    padding: '10px 14px',
    boxShadow: '0 6px 20px -10px rgba(26,26,26,0.18)',
  },
  success: {
    iconTheme: { primary: '#5B7A52', secondary: '#FFFCF7' },
  },
  error: {
    iconTheme: { primary: '#A2492F', secondary: '#FFFCF7' },
  },
};
