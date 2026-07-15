"use client";

import { ReactFlow, Background, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { RunResult } from "@/lib/types";
import { Card } from "./ui";

const nodeStyle = (active: boolean, tone: "orange" | "green" | "amber" | "zinc") => {
  const colors: Record<string, { border: string; bg: string; text: string }> = {
    orange: { border: "#f97316", bg: "#1c1005", text: "#fdba74" },
    green: { border: "#16a34a", bg: "#04170a", text: "#86efac" },
    amber: { border: "#d97706", bg: "#1c1005", text: "#fcd34d" },
    zinc: { border: "#44403c", bg: "#12100d", text: "#78716c" },
  };
  const c = active ? colors[tone] : colors.zinc;
  return {
    border: `2px solid ${c.border}`,
    background: c.bg,
    color: c.text,
    borderRadius: 0,
    boxShadow: active ? "3px 3px 0 0 #000" : "none",
    fontFamily: "var(--font-pixel), monospace",
    fontSize: 8,
    padding: "8px 10px",
    width: 160,
    textAlign: "center" as const,
  };
};

export function RoutingGraph({ run }: { run: RunResult }) {
  const winnerName =
    run.bids.find((b) => b.model_key === run.winner)?.model_name ?? "Winner";
  const hadDraft = run.winner !== null;
  const hadVerify = run.verification !== null;

  const nodes: Node[] = [
    { id: "query", position: { x: 20, y: 0 }, data: { label: "QUERY" }, style: nodeStyle(true, "orange") },
    { id: "auction", position: { x: 20, y: 70 }, data: { label: "AUCTION" }, style: nodeStyle(true, "orange") },
    { id: "winner", position: { x: 20, y: 140 }, data: { label: hadDraft ? `★ ${winnerName}` : "NO WINNER" }, style: nodeStyle(hadDraft, "green") },
    { id: "verifier", position: { x: 20, y: 210 }, data: { label: hadVerify ? `VERIFIER ${run.verification!.score.toFixed(2)}` : "VERIFIER" }, style: nodeStyle(hadVerify, run.verification?.passed ? "green" : "amber") },
    { id: "frontier", position: { x: 210, y: 245 }, data: { label: run.escalated ? `⚔ ${run.answered_by}` : "BOSS (skipped)" }, style: nodeStyle(run.escalated, "amber") },
    { id: "response", position: { x: 20, y: 300 }, data: { label: `RESPONSE · T${run.tier}` }, style: nodeStyle(true, run.tier === 1 ? "green" : "amber") },
  ];

  const edgeStyleActive = { stroke: "#f97316", strokeWidth: 2 };
  const edgeStyleDim = { stroke: "#44403c" };
  const edges: Edge[] = [
    { id: "e1", source: "query", target: "auction", animated: true, style: edgeStyleActive },
    { id: "e2", source: "auction", target: "winner", animated: hadDraft, style: hadDraft ? edgeStyleActive : edgeStyleDim },
    { id: "e3", source: "winner", target: "verifier", animated: hadVerify, style: hadVerify ? edgeStyleActive : edgeStyleDim },
    { id: "e4", source: "verifier", target: "response", animated: !run.escalated, style: !run.escalated ? edgeStyleActive : edgeStyleDim },
    { id: "e5", source: run.verification ? "verifier" : "auction", target: "frontier", animated: run.escalated, style: run.escalated ? { stroke: "#fbbf24", strokeWidth: 2 } : edgeStyleDim },
    { id: "e6", source: "frontier", target: "response", animated: run.escalated, style: run.escalated ? { stroke: "#fbbf24", strokeWidth: 2 } : edgeStyleDim },
  ];

  return (
    <Card title="Routing">
      <div className="h-95 border-2 border-stone-800 bg-black">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          zoomOnScroll={false}
          panOnDrag={false}
          preventScrolling={false}
          colorMode="dark"
        >
          <Background color="#292524" gap={16} size={2} />
        </ReactFlow>
      </div>
    </Card>
  );
}
