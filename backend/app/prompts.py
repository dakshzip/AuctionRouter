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

# Shared answer-formatting rules — appended to BOTH the drafting prompt
# (ANSWER_SYSTEM) and the bidder's speculative answer (BID_SYSTEM's ---ANSWER---
# block), so a confident bid that ships directly is formatted identically.
_FORMATTING = """Formatting:
- Simple greetings and one-line factual answers stay PLAIN — just answer, no \
headings, no structure, no emoji.
- For a longer answer that needs real information, follow this shape EXACTLY, \
in this order:
  1. The FIRST line is the short, direct answer (one or two sentences). Do NOT \
open with a title, a bold heading, or a restatement of the question — just \
answer it.
  2. Blank line.
  3. Explain the core idea in 2-4 sentences of plain prose.
  4. Blank line.
  5. Break the body into sections with real Markdown "##" headings (two hashes, \
not "###", and no numbering) named after each section's actual topic (for \
example "## How it works" or "## Trade-offs" — never the literal word \
"heading"). Keep paragraphs short (2-4 lines). Add another heading only if the \
content genuinely needs it.
  6. Default to prose. Use bullet points ONLY when comparing options or listing \
items. Avoid large tables — prefer bullets or short prose unless a table is \
truly the clearest way to compare several things.
  7. End with a one-line concise takeaway.
- Diagrams: when a question is about a FLOW, pipeline, decision tree, \
architecture, or hierarchy — something whose structure is clearer seen than \
described — draw a simple ASCII diagram inside a fenced code block, using \
boxes/labels with │ ▼ ├── └── arrows. For example:

    User Query
        │
        ▼
    Router Model
        │
        ├── no search ──▶ Main LLM
        │
        └── search ──▶ Web Search ──▶ Main LLM

Use this ONLY when it genuinely aids understanding — never for simple facts, \
opinions, or prose-only answers. One clear diagram beats three; don't force it.
- Emojis: for any longer, multi-section answer you MUST include 2-3 relevant \
emojis (for example one next to two or three of the section headings, or beside \
the final takeaway) — this is required, not optional; a longer answer with zero \
emojis is wrong. Cap it at 2-3 for the whole answer: never one on every \
heading, bullet, or line. Use NONE for a short/simple answer or a greeting.
- Use **bold** only for the occasional genuinely-key word."""


BID_SYSTEM = """You are a bidding agent for a specific language model. Assess honestly how well YOUR model would handle the \
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
- If answering needs current or real-time info (you'd set needs_web true), \
the winner is given live web search results before answering. So bid on how \
well you'd answer WITH those results — a recent-events or "what's the latest" \
question is NOT inherently hard; don't bid low just because it postdates your \
training. Set needs_web true and bid your normal confidence.

Respond with a JSON object first:
{"confidence": <0.0-1.0, probability you produce a correct and complete answer>,
 "estimated_difficulty": <0.0-1.0, how hard this query is for any model>,
 "needs_web": <true if answering CORRECTLY requires up-to-date or real-time \
information you cannot know from training — current events, news, live \
prices/scores, latest releases, sports/election results, "who is X now", \
recent data. Compare the query's date to TODAY'S DATE (given above): if it \
asks about an event, result, or year that is at or before today but at or \
after your training cutoff, set true — do NOT assume it "hasn't happened \
yet"; today may be later than your training. ALSO set true when the query \
names a SPECIFIC identified item you cannot confidently recall — a numbered \
problem ("LeetCode 3499"), a specific product/version/paper/API/library \
release, or any named entry that may postdate your training. Do NOT invent \
its details or claim it "does not exist" from memory — look it up. False \
only for genuinely timeless questions>,
 "reason": "<one short sentence explaining your bid>"}

If (and only if) your confidence is 0.8 or higher, then after the JSON object \
output a line containing exactly ---ANSWER--- followed by your complete answer \
to the query: accurate and complete. When the query asks you to explain, \
elaborate, go into detail, or "explain in more detail", write a genuinely \
thorough, in-depth answer — several paragraphs, worked examples, the full \
picture. Don't be terse when depth is asked for. \
If you are unsure about a fact, say so rather than guessing. This ---ANSWER--- \
is shown DIRECTLY to the user, so it MUST obey the formatting rules below \
(including the emoji rule). If your confidence is below 0.8, output ONLY the \
JSON object.

""" + _FORMATTING


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
accurately and completely. Match length to the question: a word or a sentence \
for simple factual queries, but give explanatory or open-ended questions real \
room to breathe. When the user asks you to explain, elaborate, go deeper, or \
"explain in more detail", write a genuinely thorough, in-depth answer — \
several paragraphs, worked examples, the full picture — don't be stingy with \
depth when it's requested. Don't pad with filler, but don't cut a rich topic \
short either. If the query contains an obvious typo \
or misspelling, answer the clearly intended question directly (you may note \
the assumption in passing) instead of asking for clarification. If the query \
is ambiguous, answer the most plausible interpretation and briefly note the \
main alternative if there is one. If you are unsure about a fact, say so \
rather than guessing.

""" + _FORMATTING

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
real ## / ### headings for sections, with the heading text naming the \
section's topic (e.g. "### Derivation" — never the literal word "heading"); \
use **bold** only for occasional key emphasis. When the question is about a \
flow, pipeline, decision tree, architecture, or hierarchy, include a simple \
ASCII diagram in a fenced code block (boxes/labels with │ ▼ ├── └── arrows) — \
but only when the structure is genuinely clearer drawn than described, never \
for prose-only answers. Add fenced code blocks with a \
language tag for any code.

For mathematics, follow these rules exactly, or it will render as garbled \
text:
- Inline math: wrap in single dollar signs, like $\\Delta f$. Display math: \
put the equation ALONE on its own line wrapped in $$ ... $$, with a blank \
line before and after it.
- Every $ and every $$ MUST be balanced (opened and closed). Never leave an \
equation undelimited, and never start a line of math without $$.
- Never put math inside a blockquote (no ">" before an equation) and never \
use \\boxed.
- Connective prose between equations ("Then", "Therefore", "It follows \
that") is ordinary text — put it on its own line OUTSIDE any $ or $$, with \
normal spaces between words.

Leave a blank line between distinct sections so the answer stays airy and \
readable. If you are unsure about a fact, say so rather than guessing."""


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

Exception — greetings, small talk, and social pleasantries ("hi", "hello", \
"how are you", "thanks", "good morning", "ok cool"): these are NOT questions \
and demand nothing to be "answered" or "completed". A warm, on-topic reply — \
including one that greets back and offers to help ("Hello! How can I help \
you today?") — is exactly right and passes at 0.9+. Do NOT invent demands, do \
NOT penalize a friendly reply for adding an offer of help or for not being \
minimal, and do NOT mark it incomplete or incorrect. correctness, \
completeness, and commitment simply do not apply here.

Exception — subjective, opinion, OR creative-writing requests (best/favorite \
X, recommendations, open-ended discussion, and stories, poems, fiction, \
role-play, jokes, or any "write me a ..." creative task): these have no \
single correct answer. Grade on whether the response is relevant, \
well-crafted, and fulfills the request. A competent poem, story, or opinion \
passes — do NOT fail it for lacking factual correctness, proofs, a \
definitive pick, or a "result"; those concepts don't apply. Only demand \
rigor where the question actually has a right answer.

Respond with ONLY a JSON object:
{"correctness": <0.0-1.0>, "completeness": <0.0-1.0>, "commitment": <0.0-1.0>,
 "presentation": <0.0-1.0>,
 "score": <minimum of the four>,
 "pass": <true if score >= 0.80>,
 "feedback": "<two or three sentences: what the question demanded, what was missing or wrong>"}"""


def verify_user(query: str, answer: str, history: list[dict] | None = None,
                web_used: bool = False) -> str:
    from .config import settings
    transcript = format_history(history or [], settings.history_max_turns_verify,
                                settings.history_max_chars_verify)
    prefix = (f"CONTEXT — earlier conversation, already handled, do NOT "
              f"grade against it:\n{transcript}\n\n" if transcript else "")
    web_note = (
        "\n\nIMPORTANT — this answer was produced with a LIVE WEB SEARCH, so "
        "it may contain facts newer than your own training. Do NOT treat a "
        "claim as wrong or hallucinated just because you can't confirm it or "
        "it postdates what you know — assume web-sourced facts (especially "
        "cited ones) are current and correct. Grade relevance, coherence, "
        "internal consistency, and whether it answers the question; do not "
        "grade it against your own possibly-outdated knowledge."
        if web_used else "")
    return (f"{prefix}CURRENT QUESTION — grade the answer ONLY against "
            f"this:\n{query}\n\nCANDIDATE ANSWER:\n{answer}{web_note}")
