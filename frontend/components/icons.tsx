/**
 * Shared inline SVG glyphs.
 *
 * Same drawing conventions throughout: 24-unit box, stroked not filled,
 * rounded caps, sized by the caller's className.
 */

function Svg({ className, children }: {
  className: string;
  children: React.ReactNode;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** Two overlapping rounded squares — the universal copy glyph. */
export function CopyIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </Svg>
  );
}

export function CheckIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <polyline points="20 6 9 17 4 12" />
    </Svg>
  );
}

/** Two arcs chasing each other — the recycle/refresh glyph. */
export function RegenerateIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-7.6-4.2" />
      <polyline points="3 16 4.4 16.8 5.2 15.4" />
      <path d="M3 12a9 9 0 0 1 9-9 9 9 0 0 1 7.6 4.2" />
      <polyline points="21 8 19.6 7.2 18.8 8.6" />
    </Svg>
  );
}

/** Rounded speech bubble — the chat tab. */
export function ChatIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.6 9.6 0 0 1-2.9-.4L3 21l1.6-4.7A8.1 8.1 0 0 1 3.6 11.5a8.4 8.4 0 0 1 9-8.4 8.4 8.4 0 0 1 8.4 8.4Z" />
    </Svg>
  );
}

/** Ascending bar chart — the analytics glyph every SaaS dashboard uses. */
export function MetricsIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <line x1="3" y1="21" x2="21" y2="21" />
      <line x1="7" y1="21" x2="7" y2="14" />
      <line x1="12" y1="21" x2="12" y2="10" />
      <line x1="17" y1="21" x2="17" y2="5" />
    </Svg>
  );
}

/** Two-lobed brain — the general topic. */
export function BrainIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      {/* Wider than it is tall: at 12px a taller silhouette just reads as a
          circle with a line down it. */}
      <path d="M12 7c-1-1.8-3.4-2.2-5-1-1.9-.3-3.6 1-3.7 2.7-1.4.8-1.7 2.5-.6 3.6-.5 1.7.8 3.4 2.7 3.5 1 1.4 3.2 1.5 4.4.2.7.5 1.6.5 2.2 0" />
      <path d="M12 7c1-1.8 3.4-2.2 5-1 1.9-.3 3.6 1 3.7 2.7 1.4.8 1.7 2.5.6 3.6.5 1.7-.8 3.4-2.7 3.5-1 1.4-3.2 1.5-4.4.2-.7.5-1.6.5-2.2 0" />
      <line x1="12" y1="7" x2="12" y2="16.3" />
    </Svg>
  );
}

/** Angle brackets — the coding topic. */
export function CodeIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <polyline points="8 6 3 12 8 18" />
      <polyline points="16 6 21 12 16 18" />
    </Svg>
  );
}

/** Sigma — the logic/math topic. */
export function SigmaIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M18 5H6l6 7-6 7h12" />
    </Svg>
  );
}

/** Gavel — the auction is running. */
export function GavelIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M14 3 21 10" />
      <path d="M17.5 6.5 13 11" />
      <path d="M12 5.5 16.5 10" />
      <path d="M12.5 10.5 4 19" />
      <line x1="3" y1="21" x2="10" y2="21" />
    </Svg>
  );
}

/** Magnifier — a live web search is in flight. */
export function SearchIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <circle cx="11" cy="11" r="7" />
      <line x1="16" y1="16" x2="21" y2="21" />
    </Svg>
  );
}

/** Balance scale — the verifier weighing the draft. */
export function ScaleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <line x1="12" y1="4" x2="12" y2="21" />
      <line x1="7" y1="21" x2="17" y2="21" />
      <line x1="4" y1="7" x2="20" y2="7" />
      <path d="M4 7 1.5 13h5Z" />
      <path d="M20 7 17.5 13h5Z" />
    </Svg>
  );
}

/** Crossed swords — the frontier model has been summoned. */
export function SwordsIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M3 3h3l11 11-3 3L3 6Z" />
      <path d="M21 3h-3L7 14l3 3L21 6Z" />
    </Svg>
  );
}

/** Triangle warning — shipped, but not vouched for. */
export function AlertIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M12 4 22 20H2Z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <line x1="12" y1="17" x2="12" y2="17" />
    </Svg>
  );
}

/** Cross — verification failed. */
export function XIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </Svg>
  );
}

/** Pencil — edit an existing prompt. */
export function PencilIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </Svg>
  );
}
