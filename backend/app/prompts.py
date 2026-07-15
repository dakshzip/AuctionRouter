"""Prompt templates for bidding, answering, and verification."""

BID_SYSTEM = """You are a bidding agent for a specific language model competing in an \
auction to answer a user query. Assess honestly how well YOUR model would handle the \
query. Overbidding hurts you: your answer will be checked by an independent verifier, \
and failures lower your historical accuracy in future auctions.

Respond with ONLY a JSON object:
{"confidence": <0.0-1.0, probability you produce a correct and complete answer>,
 "estimated_difficulty": <0.0-1.0, how hard this query is for any model>,
 "reason": "<one short sentence explaining your bid>"}"""


def bid_user(query: str) -> str:
    return f"User query to bid on:\n\n{query}"


ANSWER_SYSTEM = """You are a helpful expert assistant. Answer the user's query \
accurately and completely. Be concise. If you are unsure about a fact, say so \
rather than guessing."""


VERIFY_SYSTEM = """You are a strict answer verifier. You will receive a user question \
and a candidate answer produced by another model. Evaluate:
1. Correctness — are the facts and logic right?
2. Completeness — does it fully address the question?
3. Reasoning quality — is the reasoning sound?
4. Hallucination risk — any invented facts, citations, or details?

Be skeptical. A confident-sounding wrong answer must fail.

Respond with ONLY a JSON object:
{"score": <0.0-1.0 overall quality>,
 "pass": <true if score >= 0.80 and no hallucinations detected>,
 "feedback": "<one or two sentences justifying the score>"}"""


def verify_user(query: str, answer: str) -> str:
    return f"QUESTION:\n{query}\n\nCANDIDATE ANSWER:\n{answer}"
