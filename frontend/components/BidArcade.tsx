"use client";

import { useEffect, useState } from "react";

// 8-bit idle animation: the three tier-1 models bidding at an auction.
// Pure CSS pixel art — each sprite is a grid of colored cells.

const BOTS = [
  { name: "DEEPSEEK", color: "#38bdf8", dark: "#075985" },
  { name: "QWEN-CODER", color: "#a3e635", dark: "#3f6212" },
  { name: "NEMOTRON", color: "#fb923c", dark: "#9a3412" },
];

// 8x8 robot sprite: 0 empty, 1 body, 2 eye, 3 antenna
const SPRITE = [
  [0, 0, 0, 3, 3, 0, 0, 0],
  [0, 0, 0, 1, 1, 0, 0, 0],
  [0, 1, 1, 1, 1, 1, 1, 0],
  [0, 1, 2, 1, 1, 2, 1, 0],
  [0, 1, 1, 1, 1, 1, 1, 0],
  [0, 1, 1, 2, 2, 1, 1, 0],
  [0, 0, 1, 1, 1, 1, 0, 0],
  [0, 1, 1, 0, 0, 1, 1, 0],
];

function Sprite({ color, dark }: { color: string; dark: string }) {
  return (
    <div
      className="grid"
      style={{
        gridTemplateColumns: "repeat(8, 5px)",
        gridTemplateRows: "repeat(8, 5px)",
      }}
    >
      {SPRITE.flat().map((cell, i) => (
        <div
          key={i}
          style={{
            background:
              cell === 1 ? color : cell === 2 ? "#0c0a08" : cell === 3 ? dark : "transparent",
          }}
        />
      ))}
    </div>
  );
}

export function BidArcade() {
  const [bids, setBids] = useState([0.72, 0.55, 0.63]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setBids((prev) => prev.map(() => 0.35 + Math.random() * 0.6));
      setTick((t) => t + 1);
    }, 1600);
    return () => clearInterval(id);
  }, []);

  const leader = bids.indexOf(Math.max(...bids));

  return (
    <div className="pixel-panel glow-border p-4">
      <h3 className="mb-1 font-[family-name:var(--font-pixel)] text-[10px] uppercase tracking-wider text-orange-500">
        ▚ Live Auction House
      </h3>
      <p className="mb-4 text-sm text-stone-500">
        waiting for a query… the bots are warming up
      </p>

      <div className="border-2 border-stone-800 bg-black px-3 pb-3 pt-6">
        {/* podium row */}
        <div className="flex items-end justify-around">
          {BOTS.map((bot, i) => (
            <div key={bot.name} className="flex flex-col items-center gap-1">
              {/* bid bubble */}
              <div
                key={`${tick}-${i}`}
                className="bid-pop font-[family-name:var(--font-pixel)] text-[8px] text-stone-300"
                style={{ color: i === leader ? bot.color : undefined }}
              >
                {i === leader ? "★" : ""}BID {bids[i].toFixed(2)}
              </div>
              <div
                className="bidder-bounce"
                style={{ animationDelay: `${i * 0.2}s` }}
              >
                <Sprite color={bot.color} dark={bot.dark} />
              </div>
              <div
                className="mt-1 font-[family-name:var(--font-pixel)] text-[7px]"
                style={{ color: i === leader ? bot.color : "#57534e" }}
              >
                {bot.name}
              </div>
              {/* podium block */}
              <div
                className="h-3 w-12 border-2 border-stone-700"
                style={{
                  background: i === leader ? "#1c1005" : "#12100d",
                  borderColor: i === leader ? bot.color : undefined,
                }}
              />
            </div>
          ))}
        </div>

        {/* auctioneer gavel */}
        <div className="mt-4 flex items-center justify-center gap-2 border-t-2 border-dashed border-stone-800 pt-3">
          <span className="gavel-slam inline-block text-xl">🔨</span>
          <span className="font-[family-name:var(--font-pixel)] text-[8px] text-stone-500">
            GOING ONCE… GOING TWICE…
          </span>
        </div>
      </div>
    </div>
  );
}
