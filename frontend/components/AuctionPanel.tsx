import type { RunResult } from "@/lib/types";
import { Badge, Bar, Card } from "./ui";

export function AuctionPanel({ run }: { run: RunResult }) {
  const sorted = [...run.bids].sort((a, b) => b.auction_score - a.auction_score);
  return (
    <Card title="Auction">
      <div className="space-y-4">
        {sorted.map((bid) => {
          const isWinner = bid.model_key === run.winner;
          return (
            <div
              key={bid.model_key}
              className={`border-2 p-3 ${
                isWinner
                  ? "border-orange-500 bg-orange-950/30 shadow-[3px_3px_0_0_rgba(249,115,22,0.3)]"
                  : "border-stone-700 bg-stone-950/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-[family-name:var(--font-pixel)] text-[9px] text-stone-200">
                    {isWinner ? "★ " : ""}
                    {bid.model_name}
                  </span>
                  {isWinner && <Badge tone="amber">winner</Badge>}
                  {bid.error && <Badge tone="rose">KO</Badge>}
                </div>
                <span className="text-lg text-orange-400">
                  {bid.auction_score.toFixed(3)}
                </span>
              </div>
              {bid.error ? (
                <p className="mt-1 text-sm text-red-400/80">{bid.error}</p>
              ) : (
                <>
                  <div className="mt-2 grid grid-cols-3 gap-3 text-sm text-stone-500">
                    <div>
                      <div className="flex justify-between">
                        <span>conf</span>
                        <span className="text-stone-300">
                          {bid.confidence.toFixed(2)}
                        </span>
                      </div>
                      <Bar value={bid.confidence} tone="sky" />
                    </div>
                    <div>
                      <div className="flex justify-between">
                        <span>hist</span>
                        <span className="text-stone-300">
                          {bid.historical_accuracy.toFixed(2)}
                        </span>
                      </div>
                      <Bar value={bid.historical_accuracy} tone="green" />
                    </div>
                    <div>
                      <div className="flex justify-between">
                        <span>cost</span>
                        <span className="text-stone-300">
                          {bid.cost_factor.toFixed(2)}
                        </span>
                      </div>
                      <Bar value={bid.cost_factor} tone="rose" />
                    </div>
                  </div>
                  {bid.reason && (
                    <p className="mt-2 text-sm italic text-stone-500">
                      “{bid.reason}”
                    </p>
                  )}
                </>
              )}
            </div>
          );
        })}
        <p className="text-xs text-stone-600">
          score = 0.7·conf + 0.2·hist − 0.1·cost
        </p>
      </div>
    </Card>
  );
}
