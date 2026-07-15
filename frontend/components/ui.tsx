import type { ReactNode } from "react";

export function Card({
  title,
  children,
  className = "",
  accent = false,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`pixel-panel ${accent ? "pixel-panel-accent" : ""} p-4 ${className}`}
    >
      {title && (
        <h3 className="mb-3 font-[family-name:var(--font-pixel)] text-[10px] uppercase tracking-wider text-orange-500">
          ▚ {title}
        </h3>
      )}
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "zinc",
}: {
  children: ReactNode;
  tone?: "zinc" | "green" | "amber" | "rose" | "sky";
}) {
  const tones: Record<string, string> = {
    zinc: "bg-stone-900 text-stone-400 border-stone-600",
    green: "bg-green-950 text-green-400 border-green-600",
    amber: "bg-orange-950 text-orange-400 border-orange-600",
    rose: "bg-red-950 text-red-400 border-red-600",
    sky: "bg-orange-950 text-orange-300 border-orange-700",
  };
  return (
    <span
      className={`inline-flex items-center border-2 px-1.5 font-[family-name:var(--font-pixel)] text-[8px] uppercase leading-4 ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

// Segmented pixel health-bar
export function Bar({
  value,
  tone = "sky",
}: {
  value: number; // 0..1
  tone?: "sky" | "green" | "amber" | "rose";
}) {
  const tones: Record<string, string> = {
    sky: "bg-orange-500",
    green: "bg-green-500",
    amber: "bg-amber-400",
    rose: "bg-red-500",
  };
  const SEGMENTS = 12;
  const filled = Math.round(Math.max(0, Math.min(1, value)) * SEGMENTS);
  return (
    <div className="flex h-3 w-full gap-[2px] border-2 border-stone-700 bg-black p-[2px]">
      {Array.from({ length: SEGMENTS }, (_, i) => (
        <div
          key={i}
          className={`flex-1 ${i < filled ? tones[tone] : "bg-stone-900"}`}
        />
      ))}
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="pixel-panel dither p-4">
      <div className="font-[family-name:var(--font-pixel)] text-[8px] uppercase text-stone-500">
        {label}
      </div>
      <div className="mt-2 font-[family-name:var(--font-pixel)] text-lg text-orange-400">
        {value}
      </div>
      {sub && <div className="mt-1 text-sm leading-tight text-stone-500">{sub}</div>}
    </div>
  );
}
