"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { streamQuery, type QueryHint } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import {
  CheckIcon,
  CodeIcon,
  CopyIcon,
  PencilIcon,
  RegenerateIcon,
  SigmaIcon,
  SparkleIcon,
} from "./icons";
import type { ChatTurn, RunResult, SourceImage } from "@/lib/types";
import { Badge } from "./ui";
import { ImageStrip } from "./ImageStrip";
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
  // Web-search thumbnails, when the search turned up image-worthy results
  images: SourceImage[];
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
  "> tip: ask about current events — GAVL keeps up to date",
  "> tip: ask something really tough — GAVL calls in its smartest model",
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

// Icon buttons under an answer. Glyphs live in ./icons so the code-block
// copy button in Markdown.tsx draws from the same set.
function IconButton({
  onClick,
  title,
  children,
  active = false,
}: {
  onClick: () => void;
  title: string;
  children: ReactNode;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      // Confirmation lands in GAVL orange rather than a generic green
      className={active ? "text-orange-400" : "text-stone-600 hover:text-orange-400"}
    >
      {children}
    </button>
  );
}

/** Copy the answer's raw markdown, with the same 1.5s tick as code blocks. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <IconButton
      title={copied ? "copied" : "copy answer"}
      active={copied}
      onClick={async () => {
        if (!(await copyText(text))) return;
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
    </IconButton>
  );
}

function RegenerateButton({ onClick }: { onClick: () => void }) {
  return (
    <IconButton onClick={onClick} title="regenerate">
      <RegenerateIcon />
    </IconButton>
  );
}

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
  // Inline prompt editing: index of the user message being edited, if any
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
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
    setInput("");
    runQuery(query, messages);
  }

  // Abort handle for the in-flight stream; "stop generating" fires this
  const abortRef = useRef<AbortController | null>(null);

  function stop() {
    abortRef.current?.abort();
  }

  function startEdit(i: number, text: string) {
    if (live) return;
    setEditingIdx(i);
    setEditText(text);
  }

  function cancelEdit() {
    setEditingIdx(null);
    setEditText("");
  }

  /** Re-ask an edited question, dropping every turn that followed it. */
  function submitEdit(i: number) {
    const text = editText.trim();
    const unchanged = text === messages[i]?.text;
    cancelEdit();
    if (!text || unchanged) return;
    runQuery(text, messages.slice(0, i));
  }

  /** Re-ask the last question, dropping the answer it produced. */
  function regenerate() {
    if (live) return;
    const idx = messages.map((m) => m.role).lastIndexOf("user");
    if (idx < 0) return;
    runQuery(messages[idx].text, messages.slice(0, idx));
  }

  /**
   * Run `query` with `prefix` as the conversation before it.
   *
   * Taking the prefix as an argument rather than reading `messages` is what
   * lets edit and regenerate rewrite history: they pass a truncated slice, and
   * everything after the edited turn is dropped.
   */
  async function runQuery(query: string, prefix: ChatMessage[]) {
    if (live) return;
    // Prior turns (excluding errors) give the pipeline conversation context
    const history: ChatTurn[] = prefix
      .filter((m) => m.role !== "error")
      .slice(-12)
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.text.slice(0, 8000),
      }));
    // Assignment, not append — this is the truncation
    setMessages([...prefix, { role: "user", text: query }]);
    const controller = new AbortController();
    abortRef.current = controller;
    setLive({
      status: "⚡ AUCTION IN PROGRESS…",
      text: "",
      escalating: false,
      searching: false,
      // Hedge tokens stream during the auction, before any verdict
      provisional: true,
      thinking: "",
      images: [],
    });
    scroll();
    try {
      await streamQuery(query, history, hint, (ev) => {
        // A stopped stream can still have a queued event in flight; drop it
        // rather than let it repopulate the bubble we just cleared.
        if (controller.signal.aborted) return;
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
                images: [],
              });
            }
            break;
          case "token":
            pendingRef.current += ev.text ?? "";
            break;
          case "reset":
            // The streamed provisional draft lost the auction — clear it
            pendingRef.current = "";
            setLive((l) => l && { ...l, text: "", images: [] });
            break;
          case "images":
            setLive((l) => l && { ...l, images: ev.images ?? [] });
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
      }, controller.signal);
    } catch (e) {
      // A user-initiated stop is not a failure: the partial answer is
      // discarded silently, leaving the question in place to retry or edit.
      if (!controller.signal.aborted) {
        setMessages((m) => [...m, { role: "error", text: String(e) }]);
      }
    } finally {
      pendingRef.current = "";
      abortRef.current = null;
      setLive(null);
      scroll();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto pr-2">
        {/* Centered on the same axis as the composer, a touch narrower than
            it (70rem) so the answers sit just inside the input pill. */}
        <div className="mx-auto flex min-h-full w-full max-w-[66rem] flex-col space-y-4 px-3">
        {messages.length === 0 && !live && (
          <div className="flex flex-1 items-center justify-center">
            <div className="whitespace-nowrap px-5 text-center font-[family-name:var(--font-pixel)] text-sm leading-relaxed text-stone-300">
              No limits to curiosity. Ask anything.
            </div>
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="group flex items-center justify-end gap-2">
              {/* Edit affordance sits outside the pill, revealed on hover */}
              {editingIdx === null && !live && (
                <div className="opacity-0 transition-opacity group-hover:opacity-100">
                  <IconButton
                    title="edit prompt"
                    onClick={() => startEdit(i, msg.text)}
                  >
                    <PencilIcon />
                  </IconButton>
                </div>
              )}
              {editingIdx === i ? (
                <div className="w-full max-w-[80%] rounded-2xl bg-orange-950/60 px-4 py-2 text-orange-100">
                  <textarea
                    autoFocus
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        submitEdit(i);
                      } else if (e.key === "Escape") {
                        cancelEdit();
                      }
                    }}
                    rows={2}
                    className="w-full resize-none bg-transparent text-orange-100 outline-none"
                  />
                  <div className="mt-1 flex justify-end gap-3 font-[family-name:var(--font-pixel)] text-[10px] uppercase">
                    <button
                      onClick={cancelEdit}
                      className="text-stone-400 hover:text-stone-200"
                    >
                      cancel
                    </button>
                    <button
                      onClick={() => submitEdit(i)}
                      className="text-orange-400 hover:text-orange-300"
                    >
                      send
                    </button>
                  </div>
                </div>
              ) : (
                <div className="max-w-[80%] rounded-full bg-orange-950/60 px-4 py-2 text-orange-100">
                  <span className="mr-1 text-orange-500">&gt;</span>
                  {msg.text}
                </div>
              )}
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
                className={`w-full cursor-pointer select-text px-6 py-2 text-left ${
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
                <div className="text-stone-100">
                  <Markdown>{msg.text}</Markdown>
                </div>
                <ImageStrip images={msg.run?.images} />
                {/* Copy on every answer; regenerate only on the last, since
                    re-asking mid-thread would discard the turns after it.
                    Both hidden for /explain, which isn't pipeline output. */}
                {!live && msg.text !== EXPLAIN_TEXT && (
                  <div
                    className="mt-2 flex items-center gap-3"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <CopyButton text={msg.text} />
                    {i === messages.length - 1 && (
                      <RegenerateButton onClick={regenerate} />
                    )}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        {/* Stopped mid-answer: the question is left standing on its own, so
            offer the retry here rather than making the user retype it. */}
        {!live && messages.length > 0 &&
          messages[messages.length - 1].role === "user" && (
            <div className="flex justify-start px-6">
              <RegenerateButton onClick={regenerate} />
            </div>
          )}
        {live && (
          <div className="flex justify-start">
            <div
              className={`w-full px-6 py-2 ${
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
                <div className="text-stone-100">
                  <Markdown highlight={false}>{live.text}</Markdown>
                </div>
              )}
              <ImageStrip images={live.images} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-[70rem]">
      <div className="mt-1 flex flex-wrap items-center gap-1.5 pl-8">
        {(
          [
            ["general", "general", SparkleIcon],
            ["coding", "coding", CodeIcon],
            ["reasoning", "logic/math", SigmaIcon],
          ] as [QueryHint, string, typeof SparkleIcon][]
        ).map(([value, label, Icon]) => (
          <button
            key={value}
            onClick={() => setHint(value)}
            className={`flex items-center justify-center gap-1.5 rounded px-2 py-1 font-[family-name:var(--font-pixel)] text-[10px] leading-none uppercase ${
              hint === value
                ? "bg-orange-950 text-orange-400"
                : "bg-stone-900 text-stone-500 hover:text-stone-300"
            }`}
            title="picks which model pre-drafts your answer during the auction"
          >
            <Icon className="h-3 w-3" />
            {label}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex items-center gap-3 pl-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={1}
          placeholder={PLACEHOLDERS[phIdx]}
          // ChatGPT's composer is #303030 against a #212121 page — a small
          // lift. This page is pure black (globals.css --background), so the
          // same hex reads far brighter here. Matching the *contrast* rather
          // than the value: neutral grey, barely above the background.
          className="w-full resize-none rounded-full bg-[#1a1a1a] px-6 py-3.5 text-left text-stone-100 outline-none placeholder:text-stone-400"
        />
        {/* One button, two jobs: send when idle, stop while streaming —
            it's the only control that stays live mid-answer. */}
        <button
          onClick={live ? stop : send}
          disabled={!live && !input.trim()}
          aria-label={live ? "stop generating" : "send"}
          title={live ? "stop generating" : "send"}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-orange-950 text-orange-400 hover:text-orange-300 disabled:cursor-not-allowed disabled:text-stone-600"
        >
          <svg
            viewBox="0 0 24 24"
            fill={live ? "currentColor" : "none"}
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5"
          >
            {live ? (
              <rect x="7" y="7" width="10" height="10" rx="1.5" />
            ) : (
              <path d="M5 12h14M13 6l6 6-6 6" />
            )}
          </svg>
        </button>
      </div>
      </div>
    </div>
  );
}
