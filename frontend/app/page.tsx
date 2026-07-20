"use client";

import { useEffect, useState } from "react";
import { AccessGate } from "@/components/AccessGate";
import { AuctionPanel } from "@/components/AuctionPanel";
import { BidArcade } from "@/components/BidArcade";
import { Chat } from "@/components/Chat";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { RoutingGraph } from "@/components/RoutingGraph";
import { VerificationPanel } from "@/components/VerificationPanel";
import { fetchHealth, getAccessCode, onAuthFailure } from "@/lib/api";
import type { RunResult } from "@/lib/types";

type Tab = "chat" | "metrics";

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [selectedRun, setSelectedRun] = useState<RunResult | null>(null);
  const [runCount, setRunCount] = useState(0);
  const [sideOpen, setSideOpen] = useState(false);
  // null until we've checked sessionStorage (avoids a gate flash on reload)
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const [rejected, setRejected] = useState(false);

  useEffect(() => {
    // Skip the gate entirely when the backend has no access code (local dev)
    fetchHealth()
      .then((h) => setUnlocked(!h.access_required || !!getAccessCode()))
      .catch(() => setUnlocked(!!getAccessCode()));
    // A 401 mid-session (wrong/expired code) bounces back to the gate
    onAuthFailure(() => {
      setUnlocked(false);
      setRejected(true);
    });
  }, []);

  if (unlocked === null) return null;
  if (!unlocked)
    return (
      <AccessGate
        rejected={rejected}
        onUnlock={() => {
          setRejected(false);
          setUnlocked(true);
        }}
      />
    );

  return (
    <div className="mx-auto flex h-dvh w-full flex-col px-3 py-3 sm:px-6 sm:py-4">
      <header className="mb-3 flex items-center justify-between gap-2 px-1 py-1 sm:mb-4 sm:py-2">
        <h1 className="crt font-[family-name:var(--font-pixel)] text-base tracking-tight text-stone-200 sm:text-2xl">
          AUCTION
          <span className="glow-pulse text-orange-500">ROUTER</span>
          <span className="blink text-orange-500">_</span>
        </h1>
        <nav className="flex gap-2">
          {(["chat", "metrics"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`border-2 px-2.5 py-1.5 font-[family-name:var(--font-pixel)] text-[10px] uppercase sm:px-4 sm:py-2 sm:text-[12px] ${
                tab === t
                  ? "glow-text border-orange-500 bg-orange-950 text-orange-400 shadow-[3px_3px_0_0_#7c2d12]"
                  : "border-stone-700 bg-stone-950 text-stone-500 hover:border-stone-500 hover:text-stone-300"
              }`}
            >
              {tab === t ? `▶ ${t}` : t}
            </button>
          ))}
        </nav>
      </header>

      {/* Both tabs stay mounted (hidden via CSS) so the chat conversation
          and any in-flight query survive switching to metrics and back */}
      <div
        className={`min-h-0 flex-1 gap-2 ${
          tab === "chat" ? "flex" : "hidden"
        }`}
      >
        {/* On mobile the sidebar takes over the row, so hide the chat when
            it's open; both show side by side from sm up */}
        <section
          className={`min-h-0 min-w-0 flex-1 ${sideOpen ? "hidden sm:block" : ""}`}
        >
          <Chat
            onRun={(run) => {
              setSelectedRun(run);
              setRunCount((c) => c + 1);
            }}
            selectedRunId={selectedRun?.id ?? null}
            onSelectRun={(run) => {
              setSelectedRun(run);
              setSideOpen(true); // inspecting a run implies wanting the panels
            }}
          />
        </section>
        {/* One-arrow toggle for the routing/auction/verification sidebar */}
        <button
          onClick={() => setSideOpen((o) => !o)}
          title={sideOpen ? "hide run details" : "show run details"}
          className="flex w-6 shrink-0 items-center justify-center border-2 border-stone-800 bg-stone-950 font-[family-name:var(--font-pixel)] text-[10px] text-stone-500 hover:border-stone-600 hover:text-orange-400"
        >
          {sideOpen ? "▶" : "◀"}
        </button>
        {sideOpen && (
          <aside className="min-h-0 w-full shrink-0 space-y-4 overflow-y-auto pb-2 pr-1 sm:w-[360px]">
            {selectedRun ? (
              <>
                <RoutingGraph run={selectedRun} />
                <AuctionPanel run={selectedRun} />
                <VerificationPanel run={selectedRun} />
              </>
            ) : (
              <BidArcade />
            )}
          </aside>
        )}
      </div>
      <div
        className={`min-h-0 flex-1 overflow-y-auto pb-2 pr-2 ${
          tab === "metrics" ? "" : "hidden"
        }`}
      >
        <MetricsDashboard refreshKey={runCount} />
      </div>
    </div>
  );
}
