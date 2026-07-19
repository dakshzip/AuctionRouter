"use client";

import { useState } from "react";
import { AuctionPanel } from "@/components/AuctionPanel";
import { BidArcade } from "@/components/BidArcade";
import { Chat } from "@/components/Chat";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { RoutingGraph } from "@/components/RoutingGraph";
import { VerificationPanel } from "@/components/VerificationPanel";
import type { RunResult } from "@/lib/types";

type Tab = "chat" | "metrics";

export default function Home() {
  const [tab, setTab] = useState<Tab>("chat");
  const [selectedRun, setSelectedRun] = useState<RunResult | null>(null);
  const [runCount, setRunCount] = useState(0);
  const [sideOpen, setSideOpen] = useState(false);

  return (
    <div className="mx-auto flex h-screen w-full flex-col px-6 py-4">
      <header className="mb-4 flex items-center justify-between px-1 py-2">
        <h1 className="font-[family-name:var(--font-pixel)] text-2xl tracking-tight text-stone-200">
          AUCTION
          <span className="glow-pulse text-orange-500">ROUTER</span>
          <span className="blink text-orange-500">_</span>
        </h1>
        <nav className="flex gap-2">
          {(["chat", "metrics"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`border-2 px-4 py-2 font-[family-name:var(--font-pixel)] text-[9px] uppercase ${
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
        <section className="min-h-0 min-w-0 flex-1">
          <Chat
            onRun={(run) => {
              setSelectedRun(run);
              setRunCount((c) => c + 1);
            }}
            selectedRunId={selectedRun?.id ?? null}
            onSelectRun={setSelectedRun}
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
          <aside className="min-h-0 w-[360px] shrink-0 space-y-4 overflow-y-auto pb-2 pr-1">
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
