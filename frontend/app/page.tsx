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

  return (
    <div className="mx-auto flex h-screen w-full flex-col px-6 py-4">
      <header className="dither glow-border mb-4 flex items-center justify-between border-2 border-orange-900 bg-[#0a0806] px-6 py-5">
        <div>
          <h1 className="font-[family-name:var(--font-pixel)] text-2xl tracking-tight text-stone-200">
            AUCTION
            <span className="glow-pulse text-orange-500">ROUTER</span>
            <span className="blink text-orange-500">_</span>
          </h1>
          <p className="mt-2 text-base leading-none text-stone-500">
            cheap models bid → winner drafts → verifier judges → bosses escalate
          </p>
        </div>
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

      {tab === "chat" ? (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1fr_440px]">
          <section className="pixel-panel min-h-0 p-4">
            <Chat
              onRun={(run) => {
                setSelectedRun(run);
                setRunCount((c) => c + 1);
              }}
              selectedRunId={selectedRun?.id ?? null}
              onSelectRun={setSelectedRun}
            />
          </section>
          <aside className="min-h-0 space-y-4 overflow-y-auto pb-2 pr-2">
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
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto pb-2 pr-2">
          <MetricsDashboard refreshKey={runCount} />
        </div>
      )}
    </div>
  );
}
