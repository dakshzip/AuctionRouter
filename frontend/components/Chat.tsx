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
  searching: boolean;
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

// Rotating ticker while the web search runs (no live text yet)
const SEARCH_PHRASES = [
  "searching the web…",
  "reading results…",
  "cross-referencing sources…",
  "checking the latest…",
  "following the citations…",
  "gathering fresh intel…",
];

// Rotating input-box placeholders. Index 0 is always the opening greeting.
const PLACEHOLDERS = [
  "> Hi, what's going on?",
  "> tip: type /explain to see how the auction works",
  "> tip: use the general / coding / logic-math toggle",
  "> tip: ask about current events — it searches the web",
  "> tip: hard STEM questions summon the frontier model",
  "> tip: click any answer to inspect its bids & score",
];

// Prewritten answer for the /explain command (rendered as Markdown)
const EXPLAIN_TEXT = `## How GAVL works

Most chat apps send every question to one big, expensive model. GAVL doesn't. For each query it runs a tiny **auction**, lets cheap specialist models compete to answer, checks the winner's work, and only calls an expensive frontier model for the genuinely hard questions. You get frontier-quality answers without paying frontier prices on the easy majority.

### 1. The bidders

Three cheap, fast models sit on the panel, each a specialist:

- a **generalist** for everyday questions, knowledge, and writing
- a **coder** for programming, debugging, and software architecture
- a **logic/math** model for reasoning and quantitative problems

When your query arrives, all three bid **in parallel**. Each returns a confidence (how well it thinks it would answer), a difficulty estimate, and a flag for whether the question needs live web data. A confident bidder also drafts its full answer on the spot, so if it wins there is no extra round-trip and you see text almost immediately.

### 2. The auction

Bids are scored so that a model which is confident, has a good track record, and is cheap tends to win. The **topic toggle** above the input (general / coding / logic-math) lets you steer: it gives that model priority when it bids confidently. And the track record is *learned* -- a model that overbids and then fails verification is trusted a little less next time.

### 3. Verification

The winning draft is graded by an **independent verifier** on correctness, completeness, and commitment. This is what catches a confident-but-wrong answer before it reaches you. Creative writing (stories, poems) skips this step, since there is no single correct answer to grade against.

### 4. Escalation -- the "boss fight"

If a **genuinely hard** query fails verification, GAVL escalates to a frontier model: the boss. The bidders' difficulty estimate decides how hard it thinks and how long it is allowed to deliberate. Crucially, **easy questions never escalate** -- a weak answer to an easy question just ships (clearly marked unverified) rather than burning frontier money on something that does not need it.

### 5. Web search

If a bidder flags that answering correctly needs current information -- breaking news, latest releases, sports or election results, "who is X now", or a specific recent item it cannot recall -- the winner runs a live **web search** and cites its sources, instead of guessing from stale training data.

---

**The result:** most questions are answered in a few seconds by a cheap model, quality-checked by the verifier, and grounded on the web when they need to be, while the expensive frontier model is reserved for the small fraction of questions that truly require it. Frontier-level answers, a fraction of the cost.

*Tip: try a toggle, ask a current-events question to watch it search, or ask something genuinely hard to summon the boss.*`;

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
  // Input-box placeholder rotates every 10s; starts on the greeting (idx 0)
  const [phIdx, setPhIdx] = useState(0);
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

  // Boss / search tickers show only before any answer text
  const bossThinking = !!live?.escalating && !live.text;
  const searchingActive = !!live?.searching && !live.text;
  const tickerOn = bossThinking || searchingActive;
  useEffect(() => {
    if (!tickerOn) return;
    setTick(0);
    // Hold the opener (e.g. "someone called the boss??") ~7s, then rotate
    let interval: ReturnType<typeof setInterval> | undefined;
    const hold = setTimeout(() => {
      setTick(1);
      interval = setInterval(() => setTick((t) => t + 1), 2200);
    }, 7000);
    return () => {
      clearTimeout(hold);
      if (interval) clearInterval(interval);
    };
  }, [tickerOn]);

  // Cycle the input-box placeholder every 10s
  useEffect(() => {
    const id = setInterval(
      () => setPhIdx((i) => (i + 1) % PLACEHOLDERS.length),
      10000,
    );
    return () => clearInterval(id);
  }, []);

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
    // Local command: /explain prints a prewritten walkthrough, no pipeline
    if (query.toLowerCase() === "/explain") {
      setInput("");
      setMessages((m) => [
        ...m,
        { role: "user", text: query },
        { role: "assistant", text: EXPLAIN_TEXT },
      ]);
      scroll();
      return;
    }
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
      searching: false,
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
            else if (ev.stage === "searching")
              setLive((l) =>
                l && {
                  ...l,
                  status: "🔍 SEARCHING THE WEB…",
                  searching: true,
                  provisional: true,
                },
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
                searching: false,
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
            <div className="max-w-md px-5 text-center font-[family-name:var(--font-pixel)] text-sm leading-relaxed text-stone-300">
              No limits to curiosity. Ask anything.
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
                className={`max-w-[58%] cursor-pointer select-text px-3 py-2 text-left ${
                  msg.run && msg.run.id === selectedRunId
                    ? "shadow-[inset_3px_0_0_0_#f97316]"
                    : "hover:shadow-[inset_3px_0_0_0_#57534e]"
                }`}
              >
                {msg.run && (
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <Badge tone={msg.run.tier === 1 ? "green" : "amber"}>
                      {msg.run.answered_by}
                    </Badge>
                    {msg.run.escalated && <Badge tone="amber">boss fight</Badge>}
                    <span className="text-xs text-stone-600">
                      ${msg.run.total_cost_usd.toFixed(5)} ·{" "}
                      {(msg.run.latency_ms / 1000).toFixed(1)}s
                    </span>
                  </div>
                )}
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
              className={`max-w-[58%] px-3 py-2 ${
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
              {searchingActive && (
                <div className="max-w-full truncate font-mono text-xs italic text-stone-500">
                  {SEARCH_PHRASES[tick % SEARCH_PHRASES.length]}
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
          placeholder={PLACEHOLDERS[phIdx]}
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
