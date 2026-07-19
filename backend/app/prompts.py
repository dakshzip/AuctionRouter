"""Prompt templates for bidding, answering, and verification."""


def format_history(history: list[dict], max_turns: int, max_chars: int) -> str:
    """Render recent conversation turns as a compact transcript.

    Takes the most recent `max_turns` turns, truncates long turns so the
    whole transcript fits in `max_chars`, and returns "" for no history.

    The per-turn budget is fixed (max_chars / max_turns, NOT divided by
    the actual turn count) so a turn renders byte-identically on every
    query — a stable prompt prefix is what lets provider-side prompt
    caching hit as the conversation grows.
    """
    turns = history[-max_turns:] if history else []
    if not turns:
        return ""
    per_turn = max(200, max_chars // max_turns)
    lines = []
    for t in turns:
        content = t["content"]
        if len(content) > per_turn:
            content = content[:per_turn] + " […truncated]"
        lines.append(f"{t['role'].upper()}: {content}")
    return "\n".join(lines)

BID_SYSTEM = """You are a bidding agent for a specific language model competing in an \
auction to answer a user query. Assess honestly how well YOUR model would handle the \
query. Overbidding hurts you: your answer will be checked by an independent verifier, \
and failures lower your historical accuracy in future auctions.

A conversation transcript may precede the query; you are bidding on answering \
the LATEST user message in that conversation, which may depend on the context.

Calibration rules — you will be given your model's profile:
- Bid 0.9+ ONLY if the query is squarely within your stated strengths.
- If the query is outside your profile, bid 0.6 or lower even if you could \
probably produce a passable answer — another specialist will do it better.
- Subjective, opinion, or open-ended questions (best/favorite X, \
recommendations, comparisons, casual conversation) are EASY, not hard: there \
is no single correct answer to get wrong, so ambiguity alone must never \
lower your bid. Bid as high as your profile allows.
- Reserve bids below 0.5 for what is genuinely hard for any model of your \
size: long multi-step logical reasoning, graduate/PhD-level math or physics, \
or large and subtle coding tasks.
- Typos and misspellings are NOT difficulty: if the intended meaning is \
obvious ("PM of infia" means the PM of India), bid exactly as if it were \
spelled correctly. Only genuinely undecipherable queries warrant a low bid.
- Ambiguity is NOT difficulty either. Real users write underspecified \
queries constantly ("tell me about mercury", "how do I get better"); the \
right response is to answer the most plausible interpretation, and you \
should bid on your ability to do THAT. Lower your bid for ambiguity only \
when the query is so vague that no reasonable interpretation exists.

Respond with a JSON object first:
{"confidence": <0.0-1.0, probability you produce a correct and complete answer>,
 "estimated_difficulty": <0.0-1.0, how hard this query is for any model>,
 "reason": "<one short sentence explaining your bid>"}

If your confidence is below 0.8 you are not competing to win — omit the \
"reason" field, output just the two numbers, and stop.

If (and only if) your confidence is 0.8 or higher, include the "reason" and \
then after the JSON object output a line containing exactly ---ANSWER--- \
followed by your complete answer to the query: accurate, complete, and \
concise, exactly as you would deliver it to the user. The answer must follow \
the same rules as your bid: answer the intended question through obvious \
typos, answer the most plausible interpretation of an ambiguous query \
(briefly noting the main alternative), and never ask for clarification or \
refuse over phrasing — if you would need to do either, you were not 0.8 \
confident, so bid lower and output no answer. If you are unsure about a \
fact, say so rather than guessing."""


def bid_user(query: str, history: list[dict] | None = None,
             specialty: str = "") -> str:
    from .config import settings
    profile = f"YOUR MODEL'S PROFILE: {specialty}\n\n" if specialty else ""
    transcript = format_history(history or [], settings.history_max_turns_bid,
                                settings.history_max_chars_bid)
    if transcript:
        return (f"{profile}CONVERSATION SO FAR:\n{transcript}\n\n"
                f"LATEST user message to bid on:\n\n{query}")
    return f"{profile}User query to bid on:\n\n{query}"


ANSWER_SYSTEM = """You are a helpful expert assistant. Answer the user's query \
accurately and completely. Be concise. If the query contains an obvious typo \
or misspelling, answer the clearly intended question directly (you may note \
the assumption in passing) instead of asking for clarification. If the query \
is ambiguous, answer the most plausible interpretation and briefly note the \
main alternative if there is one. If you are unsure about a fact, say so \
rather than guessing."""

# Escalated queries are the hard ones — the frontier model should show its
# work rather than compress
FRONTIER_SYSTEM = """You are an expert assistant handling a question that \
smaller models could not answer reliably — the hard cases. Give a thorough, \
detailed, well-structured answer: walk through the reasoning step by step, \
show intermediate derivations and calculations, state the final result \
clearly, note assumptions and edge cases, and include relevant context or \
caveats the asker would benefit from. Prefer depth and completeness over \
brevity — do not pad with filler or restate the question, but never \
compress at the expense of understanding. Format the answer in Markdown: \
## headings for major sections, **bold** for key results and conclusions, \
fenced code blocks with a language tag for any code, and LaTeX \\( ... \\) \
or \\[ ... \\] for mathematical notation. If you are unsure about a fact, \
say so rather than guessing."""


VERIFY_SYSTEM = """You are a strict answer verifier. You will receive a user question \
and a candidate answer produced by another model.

A conversation transcript may precede the question, marked as CONTEXT. It is \
reference material only: earlier questions in it were ALREADY ANSWERED and \
impose NO demands on this answer. Grade the answer solely as a reply to the \
CURRENT QUESTION — even if the current question is short and casual while \
the context contains elaborate earlier problems. The context matters only \
when the current question refers back to it (e.g. "and what about X?"); an \
answer that ignores such a back-reference fails completeness.

Step 1 — before reading the answer, list what the CURRENT QUESTION (and \
nothing else) actually demands: every specific quantity, proof, or \
conclusion it asks for. The hardest sub-question is the one that matters \
most.

Step 2 — grade the answer against that list on four dimensions, each 0.0-1.0:
- correctness: are the facts and logic right? Verify calculations yourself.
- completeness: is every demand met? An answer that covers easy parts but \
never delivers the hard part (e.g. a section titled with the question that \
never states the result) scores LOW here, no matter how polished it looks.
- commitment: does it state results plainly and prove them? Hedging \
("provided we are clever", "this is equivalent, however..."), restating the \
question instead of answering it, or never landing on a final result is a \
failure of commitment.
- presentation: leaked thinking-out-loud ("Wait...", "Hmm...", "let me \
recalculate", abandoned attempts, self-contradictions, conflicting final \
values) caps this at 0.5.

The overall score is the MINIMUM of the four — an answer is only as good as \
its weakest dimension. Calibration: 0.9+ means an expert would sign off on it \
as complete and correct; 0.7 means right but with real gaps; 0.5 means \
correct skeleton, core question not actually answered; below 0.3 means wrong \
or off-topic.

Be skeptical. Confident-sounding and shallow must fail. Correct-but-evasive \
must fail.

If the question contains an obvious typo, grade the answer against the \
clearly intended question ("PM of infia" = PM of India); answering the \
intended question directly is correct, and refusing to answer over a \
decipherable typo is a completeness failure.

If the question is ambiguous or underspecified (normal in real usage), an \
answer that addresses the most plausible interpretation — optionally noting \
the alternatives — is CORRECT and COMPLETE. Do not fail an answer for not \
resolving ambiguity the question itself left open, and do not demand \
coverage of every possible reading.

Exception — subjective or opinion questions (best/favorite X, \
recommendations, open-ended discussion): these have no single correct \
answer. Grade on whether the answer is reasonable, relevant, and \
well-organized. Do NOT fail commitment for offering a balanced view instead \
of one definitive pick, and do NOT demand proofs or exact results where none \
exist. Only demand rigor where the question actually has a right answer.

Respond with ONLY a JSON object:
{"correctness": <0.0-1.0>, "completeness": <0.0-1.0>, "commitment": <0.0-1.0>,
 "presentation": <0.0-1.0>,
 "score": <minimum of the four>,
 "pass": <true if score >= 0.80>,
 "feedback": "<two or three sentences: what the question demanded, what was missing or wrong>"}"""


def verify_user(query: str, answer: str, history: list[dict] | None = None) -> str:
    from .config import settings
    transcript = format_history(history or [], settings.history_max_turns_verify,
                                settings.history_max_chars_verify)
    prefix = (f"CONTEXT — earlier conversation, already handled, do NOT "
              f"grade against it:\n{transcript}\n\n" if transcript else "")
    return (f"{prefix}CURRENT QUESTION — grade the answer ONLY against "
            f"this:\n{query}\n\nCANDIDATE ANSWER:\n{answer}")
