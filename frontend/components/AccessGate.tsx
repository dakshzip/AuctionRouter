"use client";

import { useState } from "react";
import { setAccessCode } from "@/lib/api";
import { BidArcade } from "./BidArcade";

// Simple shared-code gate. Not real auth — one code shared with viewers —
// but it stops anonymous bots from spending the owner's API credits. The
// code is entered at runtime and kept in sessionStorage, never in the bundle.
export function AccessGate({
  onUnlock,
  rejected = false,
}: {
  onUnlock: () => void;
  rejected?: boolean;
}) {
  const [code, setCode] = useState("");

  function submit() {
    const c = code.trim();
    if (!c) return;
    setAccessCode(c);
    onUnlock();
  }

  return (
    <div className="flex h-screen items-center justify-center px-6">
      <div className="w-full max-w-sm space-y-4 text-center">
        <h1 className="crt font-[family-name:var(--font-pixel)] text-3xl text-stone-200">
          GA
          <span className="glow-pulse text-orange-500">VL</span>
          <span className="blink text-orange-500">_</span>
        </h1>
        <p className="font-[family-name:var(--font-pixel)] text-[10px] uppercase leading-relaxed text-orange-500/80">
          Ask more, know faster, pay less
        </p>

        {/* the bots warming up — same auction animation shown before a query */}
        <div className="text-left">
          <BidArcade />
        </div>

        <p className="text-sm text-stone-500">
          this demo needs an invite code to keep it free for everyone. enter
          the code you were given.
        </p>
        <input
          type="password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="invite code"
          autoFocus
          className="w-full border-2 border-stone-700 bg-black px-3 py-2 text-center text-stone-200 outline-none placeholder:text-stone-600 focus:border-orange-500"
        />
        {rejected && (
          <p className="text-sm text-red-400">
            that code didn&apos;t work — try again.
          </p>
        )}
        <button
          onClick={submit}
          disabled={!code.trim()}
          className="pixel-btn w-full bg-orange-950 py-2 font-[family-name:var(--font-pixel)] text-[12px] uppercase text-orange-400 disabled:text-stone-600"
        >
          enter
        </button>
      </div>
    </div>
  );
}
