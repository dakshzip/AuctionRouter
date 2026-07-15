"use client";

import { useRef, useState } from "react";
import { submitQuery } from "@/lib/api";
import type { RunResult } from "@/lib/types";
import { Badge } from "./ui";
import { Markdown } from "./Markdown";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  run?: RunResult;
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
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send() {
    const query = input.trim();
    if (!query || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: query }]);
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    try {
      const run = await submitQuery(query);
      setMessages((m) => [...m, { role: "assistant", text: run.answer, run }]);
      onRun(run);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: String(e) }]);
    } finally {
      setBusy(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto pr-2">
        {messages.length === 0 && (
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
              <div className="max-w-[85%] border-2 border-orange-700 bg-orange-950/60 px-3 py-2 text-orange-100 shadow-[3px_3px_0_0_#000]">
                <span className="mr-1 text-orange-500">&gt;</span>
                {msg.text}
              </div>
            </div>
          ) : msg.role === "error" ? (
            <div
              key={i}
              className="border-2 border-red-800 bg-red-950/50 px-3 py-2 text-sm text-red-300 shadow-[3px_3px_0_0_#000]"
            >
              ✖ {msg.text}
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <button
                onClick={() => msg.run && onSelectRun(msg.run)}
                className={`max-w-[85%] cursor-pointer border-2 px-3 py-2 text-left shadow-[3px_3px_0_0_#000] ${
                  msg.run && msg.run.id === selectedRunId
                    ? "border-orange-500 bg-stone-900"
                    : "border-stone-700 bg-stone-950 hover:border-stone-500"
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
              </button>
            </div>
          ),
        )}
        {busy && (
          <div className="flex items-center gap-2 text-orange-500">
            <span className="blink">▓</span>
            <span className="text-sm text-stone-400">
              auction → draft → verify…
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-4 flex gap-3">
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
          placeholder="> type your query…"
          className="flex-1 resize-none border-2 border-stone-700 bg-black px-3 py-2 text-stone-200 outline-none placeholder:text-stone-600 focus:border-orange-500"
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          className="pixel-btn bg-orange-950 px-5 font-[family-name:var(--font-pixel)] text-[10px] uppercase text-orange-400 disabled:cursor-not-allowed disabled:text-stone-600"
        >
          send
        </button>
      </div>
    </div>
  );
}
