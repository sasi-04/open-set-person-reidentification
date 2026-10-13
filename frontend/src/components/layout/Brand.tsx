/**
 * The OpenID Vision mark and wordmark.
 *
 * In plain words: the icon is two overlapping rings - a query and a reference being compared -
 * with a red tick in the overlap, the "verified decision". It is original artwork. This is an
 * independent prototype, so it deliberately does not use Zed Digital's logo or name as a brand.
 * The same drawing is used for the favicon (public/favicon.svg), the loading screen, empty
 * states and the exported reports.
 */
export function BrandMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className={`${className} shrink-0`}>
      <rect width="32" height="32" rx="8" fill="#14181e" stroke="#2a3039" />
      <circle cx="12.4" cy="16" r="6.3" fill="none" stroke="#f3f4f6" strokeWidth="2" />
      <circle cx="19.6" cy="16" r="6.3" fill="none" stroke="#f3f4f6" strokeOpacity="0.5" strokeWidth="2" />
      <path d="M13.9 16.4l1.9 2 3.6-4.3" fill="none" stroke="#E31B23" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      {!compact && (
        <div className="leading-tight">
          <div className="font-display text-[15px] font-semibold tracking-tight text-nav-ink">
            OpenID <span className="text-nav-ink-2">Vision</span>
          </div>
          <div className="text-[11px] text-nav-ink-2">Identity verification lab</div>
        </div>
      )}
    </div>
  );
}
