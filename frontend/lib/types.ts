export interface Bid {
  model_key: string;
  model_name: string;
  confidence: number;
  estimated_difficulty: number;
  reason: string;
  historical_accuracy: number;
  cost_factor: number;
  auction_score: number;
  error: string | null;
}

export interface Verification {
  score: number;
  passed: boolean;
  feedback: string;
}

export interface Usage {
  model_key: string;
  model_name: string;
  stage: "bid" | "draft" | "verify" | "escalate";
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
}

export interface RunResult {
  id: string;
  query: string;
  answer: string;
  answered_by: string;
  tier: 1 | 2;
  escalated: boolean;
  escalation_reason: string | null;
  bids: Bid[];
  winner: string | null;
  draft_answer: string | null;
  verification: Verification | null;
  usages: Usage[];
  total_cost_usd: number;
  baseline_cost_usd: number;
  latency_ms: number;
  created_at: string;
}

export interface MetricsSummary {
  total_queries: number;
  avg_cost_usd: number;
  total_cost_usd: number;
  total_saved_usd: number;
  avg_latency_ms: number;
  escalation_rate: number;
  tier1_resolution_rate: number;
  wins_by_model: Record<string, number>;
  accuracy_by_model: Record<string, number>;
}
