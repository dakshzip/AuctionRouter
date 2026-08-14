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

/** Four-point sparkle — the general/all-purpose topic. */
export function SparkleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M12 3c.6 3.9 2.1 5.4 6 6-3.9.6-5.4 2.1-6 6-.6-3.9-2.1-5.4-6-6 3.9-.6 5.4-2.1 6-6Z" />
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

/** Pencil — edit an existing prompt. */
export function PencilIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </Svg>
  );
}
