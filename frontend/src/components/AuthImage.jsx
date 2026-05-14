import { memo } from 'react';
import { ImageIcon } from 'lucide-react';

/**
 * Authenticated <img>. The token rides as a ?t= query param so the browser
 * handles caching, scheduling and async decode natively — no fetch+blob+
 * objectURL round-trip. ``priority`` raises this image to ``fetchpriority=high``
 * and bypasses lazy-loading; use it for the first viewport row in a grid.
 *
 * ``localSrc`` lets the caller hand in a client-side preview (e.g. produced
 * from the just-uploaded File object via ``URL.createObjectURL``) and have it
 * shown immediately, before the server preview is ready.
 */
function AuthImageBase({ src, alt, className, style, onClick, priority, localSrc }) {
  if (!src && !localSrc) {
    return (
      <div className={`flex items-center justify-center bg-surface-3 ${className || ''}`} style={style}>
        <ImageIcon className="w-8 h-8 text-text-faint" />
      </div>
    );
  }

  let finalSrc = localSrc;
  if (!finalSrc && src) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const sep = src.includes('?') ? '&' : '?';
    finalSrc = token ? `${src}${sep}t=${encodeURIComponent(token)}` : src;
  }

  return (
    <img
      src={finalSrc}
      alt={alt}
      className={`${className || ''} animate-fade-in`}
      style={style}
      onClick={onClick}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      fetchpriority={priority ? 'high' : 'auto'}
    />
  );
}

const AuthImage = memo(AuthImageBase);
export default AuthImage;
