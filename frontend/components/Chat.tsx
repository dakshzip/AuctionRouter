"use client";

import { useEffect, useRef, useState } from "react";
import { streamQuery, type QueryHint } from "@/lib/api";
import type { ChatTurn, RunResult } from "@/lib/types";
import { Badge } from "./ui";
import { Markdown } from "./Markdown";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  run?: RunResult;
}

interface LiveState {
  status: string;
  text: string;
  escalating: boolean;
  // Draft text streams before the verifier has judged it
  provisional: boolean;
  // Tail of GPT-5's streamed reasoning summary, when the provider sends one
  thinking: string;
}

// Condense raw reasoning into one short headline (GPT reasoning summaries
// use **bold** section titles; fall back to the latest sentence)
function reasoningSnippet(raw: string): string {
  const heads = raw.match(/\*\*([^*\n]{3,80})\*\*/g);
  let s = heads ? heads[heads.length - 1].replace(/\*\*/g, "") : "";
  if (!s) {
    const sentences = raw.replace(/[*#`]/g, "").trim().split(/(?<=[.!?])\s+/);
    s = sentences[sentences.length - 1] ?? "";
  }
  return s.trim().split(/\s+/).slice(0, 8).join(" ");
}

// Shown while the boss thinks silently; real reasoning deltas replace
// them. Index 0 is always the opener.
const BOSS_THOUGHTS = [
  "someone called the boss??",
  "reasoning…",
  "forming dependencies…",
  "consulting ancient tomes…",
  "grinding xp…",
  "charging special attack…",
  "questioning the premise…",
  "aligning brain cells…",
];

export function Chat({
  onRun,
  selectedRunId,
  onSelectRun,
}: {
  onRun: (run: RunResult) => void;
  selectedRunId: string | null;
  onSelectRun: (run: RunResult) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<LiveState | null>(null);
  const [hint, setHint] = useState<QueryHint>("general");
  const [tick, setTick] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Streamed text lands here and is animated out at a steady rate —
  // network chunks are bursty; the typewriter effect is client-side
  const pendingRef = useRef("");
  // Reasoning deltas buffer separately; backlog is capped so the ticker
  // skips ahead rather than lagging minutes behind the model
  const reasoningRef = useRef("");

  const streaming = live !== null;
  useEffect(() => {
    if (!streaming) {
      pendingRef.current = "";
      reasoningRef.current = "";
      return;
    }
    const id = setInterval(() => {
      const buf = pendingRef.current;
      if (!buf) return;
      // Deliberately slow typewriter (~60 chars/s floor, ~370/s ceiling):
      // tokens arrive early via the hedge stream, so the pacing exists to
      // be read, not to catch up (first chars still render next frame)
      const n = Math.min(6, Math.max(1, Math.ceil(buf.length / 400)));
      pendingRef.current = buf.slice(n);
      setLive((l) => l && { ...l, text: l.text + buf.slice(0, n) });
    }, 16);
    return () => clearInterval(id);
  }, [streaming]);

  // Rotate the boss-thought phrases while GPT-5 thinks silently
  const bossThinking = !!live?.escalating && !live.text;
  useEffect(() => {
    if (!bossThinking) return;
    setTick(0); // every boss fight opens on BOSS_THOUGHTS[0]
    const id = setInterval(() => setTick((t) => t + 1), 2200);
    return () => clearInterval(id);
  }, [bossThinking]);

  // One condensed reasoning headline at a time, swapped every ~7.5s —
  // raw reasoning streams far too fast to read
  useEffect(() => {
    if (!bossThinking) return;
    const update = () => {
      const snip = reasoningSnippet(reasoningRef.current);
      if (snip) setLive((l) => l && { ...l, thinking: snip });
    };
    const id = setInterval(update, 7500);
    return () => {
      clearInterval(id);
    };
  }, [bossThinking]);

  const scroll = () =>
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);

  async function send() {
    const query = input.trim();
    if (!query || live) return;
    // Prior turns (excluding errors) give the pipeline conversation context
    const history: ChatTurn[] = messages
      .filter((m) => m.role !== "error")
      .slice(-12)
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.text.slice(0, 8000),
      }));
    setInput("");
    setMessages((m) => [...m, { role: "user", text: query }]);
    setLive({
      status: "⚡ AUCTION IN PROGRESS…",
      text: "",
      escalating: false,
      // Hedge tokens stream during the auction, before any verdict
      provisional: true,
      thinking: "",
    });
    scroll();
    try {
      await streamQuery(query, history, hint, (ev) => {
        switch (ev.type) {
          case "stage":
            if (ev.stage === "bidding")
              setLive((l) => l && { ...l, status: "⚡ AUCTION IN PROGRESS…" });
            else if (ev.stage === "drafting")
              setLive((l) =>
                l && { ...l, status: `✍ ${ev.model} DRAFTING…`, provisional: true },
              );
            else if (ev.stage === "verifying")
              setLive((l) => l && { ...l, status: "🔍 VERIFIER JUDGING…" });
            else if (ev.stage === "delivering")
              setLive((l) =>
                l && {
                  ...l,
                  status:
                    ev.verified === false
                      ? `⚠ UNVERIFIED — ${ev.model}`
                      : `✓ VERIFIED — ${ev.model}`,
                  provisional: false,
                },
              );
            else if (ev.stage === "escalating") {
              // frontier rewrites from scratch: clear the failed draft
              pendingRef.current = "";
              reasoningRef.current = "";
              setLive((l) => l && {
                status: `⚔ BOSS FIGHT: ${ev.model}…`,
                text: "",
                escalating: true,
                provisional: false,
                thinking: "",
              });
            }
            break;
          case "token":
            pendingRef.current += ev.text ?? "";
            break;
          case "reset":
            // The streamed provisional draft lost the auction — clear it
            pendingRef.current = "";
            setLive((l) => l && { ...l, text: "" });
            break;
          case "reasoning":
            reasoningRef.current = (
              reasoningRef.current + (ev.text ?? "")
            ).slice(-4000);
            break;
          case "verification":
            if (!ev.passed)
              setLive((l) => l && {
                ...l,
                status: `✖ VERIFICATION FAILED (${ev.score?.toFixed(2)})`,
              });
            break;
          case "frontier_failed":
            setLive((l) => l && { ...l, status: "⚠ FRONTIER UNAVAILABLE — USING DRAFT" });
            break;
          case "error":
            throw new Error(ev.message);
          case "done":
            if (ev.run) {
              const run = ev.run;
              setMessages((m) => [...m, { role: "assistant", text: run.answer, run }]);
              onRun(run);
            }
            setLive(null);
            scroll();
            break;
        }
      });
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: String(e) }]);
    } finally {
      setLive(null);
      scroll();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pr-2">
        {messages.length === 0 && !live && (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-md border-2 border-dashed border-stone-700 p-5 text-center text-stone-500">
              <div className="mb-2 font-[family-name:var(--font-pixel)] text-[10px] text-orange-500">
                ═══ NEW GAME ═══
              </div>
              ask anything. three cheap models bid for your query, the winner
              answers, a verifier judges it, and only the hard fights summon
              the frontier boss.
            </div>
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[90%] bg-orange-950/60 px-3 py-2 text-orange-100">
                <span className="mr-1 text-orange-500">&gt;</span>
                {msg.text}
              </div>
            </div>
          ) : msg.role === "error" ? (
            <div
              key={i}
              className="bg-red-950/50 px-3 py-2 text-sm text-red-300"
            >
              ✖ {msg.text}
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div
                onClick={() => msg.run && onSelectRun(msg.run)}
                className={`max-w-[68%] cursor-pointer select-text px-3 py-2 text-left ${
                  msg.run && msg.run.id === selectedRunId
                    ? "shadow-[inset_3px_0_0_0_#f97316]"
                    : "hover:shadow-[inset_3px_0_0_0_#57534e]"
                }`}
              >
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge tone={msg.run?.tier === 1 ? "green" : "amber"}>
                    {msg.run?.answered_by}
                  </Badge>
                  {msg.run?.escalated && <Badge tone="amber">boss fight</Badge>}
                  <span className="text-xs text-stone-600">
                    ${msg.run?.total_cost_usd.toFixed(5)} ·{" "}
                    {((msg.run?.latency_ms ?? 0) / 1000).toFixed(1)}s
                  </span>
                </div>
                <div className="text-stone-200">
                  <Markdown>{msg.text}</Markdown>
                </div>
              </div>
            </div>
          ),
        )}
        {live && (
          <div className="flex justify-start">
            <div
              className={`max-w-[68%] px-3 py-2 ${
                live.escalating ? "bg-orange-950/20" : ""
              }`}
            >
              <div className="mb-1.5 flex items-center gap-2 font-[family-name:var(--font-pixel)] text-[10px] text-orange-400">
                <span className="blink">▓</span>
                {live.status}
                {live.provisional && live.text && (
                  <span className="border border-amber-700 bg-amber-950/40 px-1 text-[10px] uppercase text-amber-500">
                    unverified draft
                  </span>
                )}
              </div>
              {bossThinking && (
                <div className="max-w-full truncate font-mono text-xs italic text-stone-500">
                  {live.thinking
                    ? `${live.thinking}…`
                    : BOSS_THOUGHTS[tick % BOSS_THOUGHTS.length]}
                </div>
              )}
              {live.text && (
                <div className="text-stone-200">
                  <Markdown highlight={false}>{live.text}</Markdown>
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 font-[family-name:var(--font-pixel)] text-[10px] uppercase text-stone-600">
          topic
        </span>
        {(
          [
            ["general", "general"],
            ["coding", "coding"],
            ["reasoning", "logic/math"],
          ] as [QueryHint, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setHint(value)}
            className={`border px-2 py-0.5 font-[family-name:var(--font-pixel)] text-[10px] uppercase ${
              hint === value
                ? "border-orange-500 bg-orange-950 text-orange-400"
                : "border-stone-700 bg-stone-950 text-stone-500 hover:border-stone-500 hover:text-stone-300"
            }`}
            title="picks which model pre-drafts your answer during the auction"
          >
            {label}
          </button>
        ))}
      </div>
      <div className="mt-2 flex gap-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder="> type your query… (phd level stem questions trigger frontier)"
          className="flex-1 resize-none rounded-3xl border-2 border-stone-700 bg-black px-5 py-2 text-stone-200 outline-none placeholder:text-stone-600 focus:border-orange-500"
        />
        <button
          onClick={send}
          disabled={!!live || !input.trim()}
          className="pixel-btn bg-orange-950 px-5 font-[family-name:var(--font-pixel)] text-[12px] uppercase text-orange-400 disabled:cursor-not-allowed disabled:text-stone-600"
        >
          send
        </button>
      </div>
    </div>
  );
}
