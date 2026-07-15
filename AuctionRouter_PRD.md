# Product Requirements Document (PRD)

# AuctionRouter: Cost-Aware Multi-Agent LLM Orchestrator inspired by https://arxiv.org/pdf/2607.09600

## 1. Overview

AuctionRouter is a multi-agent AI system that minimizes inference cost while maintaining answer quality by routing requests through a hierarchy of language models.

Instead of sending every request to an expensive frontier model, the system:

1. Uses multiple low-cost models to evaluate a task.
2. Runs an auction-based selection process.
3. Generates an answer using the selected low-cost model.
4. Uses a verifier model to evaluate answer quality.
5. Escalates to a frontier model only when confidence is insufficient or verification fails.

The goal is to achieve:

- 60-80% lower inference cost
- Lower latency
- Comparable answer quality to frontier-only systems

---

## 2. Problem Statement

### Pattern A

User → GPT-5

**Pros**
- High quality

**Cons**
- Expensive
- Slow

### Pattern B

User → Cheap Model

**Pros**
- Fast
- Cheap

**Cons**
- Lower quality
- Hallucinations

The ideal system should:

- Use cheap models whenever possible
- Detect when cheap models are insufficient
- Escalate only when necessary

---

## 3. Goals

### Primary Goals

- Reduce average cost per query
- Maintain answer quality
- Demonstrate agent orchestration
- Visualize model routing decisions

### Secondary Goals

- Collect model performance data
- Compare models over time
- Provide explainable routing

---

## 4. User Personas

### AI Engineer

Wants to understand model routing and optimization.

### Recruiter

Wants to see practical multi-agent engineering.

### Developer

Wants cheaper inference than GPT-only solutions.

---

## 5. System Architecture

```text
User Query
    │
    ▼
Query Analyzer
    │
    ▼
Auction Manager
 ┌──────┼──────┐
 ▼      ▼      ▼
Gemini DeepSeek Qwen
 └──────┼──────┘
        ▼
 Bid Aggregation
        ▼
  Winner Model
        ▼
   Draft Answer
        ▼
  Verifier Agent
     │      │
   Pass   Fail
     │      │
 Return  Escalate
             ▼
      GPT-5 / Claude
             ▼
        Final Answer
```

---

## 6. Models

### Tier 1 (Open and Free Models)

- Gemini Flash
- DeepSeek
- Qwen

Responsibilities:

- Bid on tasks
- Generate low-cost answers

### Tier 2 (Frontier Models)

- GPT-5
- Claude Sonnet

Responsibilities:

- Complex reasoning
- Escalated requests

### Verifier Model (bigger but free model)

Responsibilities:

- Evaluate correctness
- Evaluate completeness
- Detect hallucinations
- Decide whether escalation is required

Potential choices:

- Gemini Flash
- GPT-5 Nano
- Qwen-based verifier

---

## 7. Auction Mechanism

Each cheap model receives the user query and returns:

```json
{
  "confidence": 0.87,
  "estimated_difficulty": 0.65,
  "reason": "Strong at coding tasks"
}
```

### Auction Score

```text
Auction Score =
0.7 × Confidence
+ 0.2 × Historical Accuracy
- 0.1 × Cost
```

The model with the highest score generates the draft answer.

---

## 8. Verification System

After answer generation, the verifier receives:

- Original question
- Generated answer

The verifier evaluates:

1. Correctness
2. Completeness
3. Reasoning quality
4. Hallucination risk

Returns:

```json
{
  "score": 0.84,
  "pass": true,
  "feedback": "Answer appears correct."
}
```

### Verification Threshold

```text
score >= 0.80
```

If the answer fails verification, the request is escalated.

---

## 9. Escalation Logic

### Condition 1

Low auction confidence:

```text
max_confidence < 0.75
```

### Condition 2

Verifier failure:

```text
verification_score < 0.80
```

### Condition 3

Strong model disagreement:

```text
Gemini  = 0.90
DeepSeek = 0.41
Qwen     = 0.37
```

High variance triggers escalation.

---

## 10. Frontend

### Chat Interface

Simple chat experience for submitting queries.

### Auction Visualization

Display:

- Model confidence
- Bid score
- Cost estimate
- Winner selection

### Verification Panel

Display:

- Verification score
- Pass / Fail status
- Escalation reason

### Routing Graph

Visualize the path:

```text
Query
  ↓
Auction
  ↓
Winner
  ↓
Verifier
  ↓
Response
```

or

```text
Query
  ↓
Auction
  ↓
Winner
  ↓
Verifier
  ↓
GPT-5 / Claude
  ↓
Response
```

---

## 11. Metrics Dashboard

Track:

### Cost Metrics

- Average cost per query
- Total cost saved

### Latency Metrics

- Average response time

### Escalation Metrics

- Escalation percentage
- Tier-1 resolution rate

### Model Metrics

- Gemini wins
- DeepSeek wins
- Qwen wins

---

## 12. Tech Stack

### Frontend

- Next.js
- React
- Tailwind
- shadcn/ui
- React Flow

### Backend

- FastAPI
- LangGraph

### Model Access

- OpenRouter

### Database

-Mongo

### Observability

- LangSmith


### Deployment (done after testing locally)

- Vercel


---

## 13. Success Metrics

Target outcomes:

- Tier-1 Resolution Rate > 70%
- Cost Reduction > 60%
- Latency Reduction > 30%
- Escalation Rate < 30%

---

## 14. Resume Value

This project demonstrates:

- Multi-agent systems
- Agent orchestration
- LLM routing
- Model evaluation
- Cost optimization
- Verification loops
- LangGraph workflows
- Production AI architecture

### Project Title

**AuctionRouter: A Cost-Aware Multi-Agent LLM Routing System with Verification-Based Escalation**
