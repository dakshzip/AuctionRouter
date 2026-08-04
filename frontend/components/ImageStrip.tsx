"use client";

import { useState } from "react";
import type { SourceImage } from "@/lib/types";

/**
 * Thumbnails from the web search, shown under an answer.
 *
 * Plain <img>: the app is a static export with `images.unoptimized`, so
 * next/image buys nothing here. Hotlinked URLs die routinely, so anything
 * that fails to load is dropped rather than left as a broken-image icon.
 */
export function ImageStrip({ images }: { images?: SourceImage[] }) {
  const [broken, setBroken] = useState<Set<string>>(new Set());

  const shown = (images ?? []).filter((im) => !broken.has(im.url));
  if (shown.length === 0) return null;

  return (
    <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
      {shown.map((im) => (
        <a
          key={im.url}
          href={im.source_url || im.url}
          target="_blank"
          rel="noopener noreferrer"
          title={im.description || undefined}
          // overflow-hidden so the image is clipped to the rounded corners
          className="shrink-0 overflow-hidden rounded-xl border border-stone-800 bg-stone-950 hover:border-orange-700"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={im.url}
            alt={im.description || "web search result"}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setBroken((b) => new Set(b).add(im.url))}
            // object-cover fills the tile with no letterboxing. The 4:3 tile is
            // close to how most web photos are framed, so the crop stays
            // shallow — object-contain avoided cropping entirely but left dead
            // space around anything that wasn't 4:3.
            // body sets image-rendering: pixelated for the retro look —
            // photos need it off or they come out crunchy
            className="h-44 w-60 object-cover object-center [image-rendering:auto]"
          />
        </a>
      ))}
    </div>
  );
}
