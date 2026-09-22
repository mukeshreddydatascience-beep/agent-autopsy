"""Failure-mode detectors. Each one looks for a specific way agents die in production."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Finding:
    mode: str
    severity: str  # high | medium
    title: str
    detail: str
    evidence: list = field(default_factory=list)  # span_ids
    wasted_tokens: int = 0
    suggestion: str = ""


def _norm_args(span) -> str:
    try:
        return json.dumps(span.input, sort_keys=True, default=str)
    except Exception:
        return str(span.input)


def detect_tool_loop(trace) -> Finding | None:
    """Same tool called 3+ times with identical arguments: the agent is stuck."""
    key_spans = {}
    for s in trace.tool_spans():
        key = (s.name, _norm_args(s))
        key_spans.setdefault(key, []).append(s)
    for (name, _), spans in key_spans.items():
        if len(spans) >= 3:
            wasted = sum(s.tokens for s in spans[1:])
            return Finding(
                mode="tool_loop",
                severity="high",
                title=f"Tool loop: '{name}' called {len(spans)}x with identical arguments",
                detail=(
                    f"The agent called {name} {len(spans)} times with the same input and "
                    f"kept going anyway. This is the classic stuck-agent pattern: the tool "
                    f"result never satisfies the planner, so it retries instead of rethinking."
                ),
                evidence=[s.span_id for s in spans],
                wasted_tokens=wasted,
                suggestion=(
                    f"Add a repeat-call circuit breaker (max 2 identical calls), and make the "
                    f"planner react to '{name}' returning the same result twice by changing "
                    f"strategy instead of retrying."
                ),
            )
    return None


def detect_error_cascade(trace) -> Finding | None:
    """A tool errors, the agent retries with the same bad input, errors again."""
    ordered = trace.ordered_spans()
    errored = [s for s in ordered if s.kind == "tool" and s.error]
    if len(errored) < 2:
        return None
    first_idx = ordered.index(errored[0])
    after = [s for s in ordered[first_idx:] if s.kind in ("llm", "tool")]
    wasted = sum(s.tokens for s in after)
    names = sorted({s.name for s in errored})
    return Finding(
        mode="error_cascade",
        severity="high",
        title=f"Error cascade: {len(errored)} tool errors, agent kept retrying",
        detail=(
            f"Tools {names} errored {len(errored)} times and the agent never changed its "
            f"approach. First error: '{errored[0].error}'. Retrying a failing tool with "
            f"the same input is pure burn."
        ),
        evidence=[s.span_id for s in errored],
        wasted_tokens=wasted,
        suggestion=(
            "Classify tool errors into retryable vs fatal. On fatal errors, force the "
            "planner to pick a different tool or escalate to the user instead of retrying."
        ),
    )


def detect_context_bloat(trace) -> Finding | None:
    """Context window filling up: truncation errors or exploding prompt sizes."""
    for s in trace.llm_spans():
        err = (s.error or "").lower()
        if "context" in err or "truncat" in err or "too long" in err or "max_tokens" in err:
            return Finding(
                mode="context_bloat",
                severity="high",
                title="Context bloat: hit the context limit mid-run",
                detail=(
                    f"LLM span '{s.span_id}' failed with: '{s.error}'. The conversation "
                    f"history grew until the model could not fit it. Everything after this "
                    f"point is garbage output on truncated context."
                ),
                evidence=[s.span_id],
                wasted_tokens=sum(x.tokens for x in trace.llm_spans()),
                suggestion=(
                    "Compact history aggressively: summarize tool results instead of "
                    "appending raw output, and cap retained history at ~50% of the window."
                ),
            )
    llms = trace.llm_spans()
    if len(llms) >= 3 and llms[0].tokens_in > 0:
        growth = llms[-1].tokens_in / llms[0].tokens_in
        if growth > 3 and llms[-1].tokens_in > 8000:
            wasted = sum(s.tokens_in for s in llms[1:])
            return Finding(
                mode="context_bloat",
                severity="medium",
                title=f"Context bloat: prompt grew {growth:.1f}x during the run",
                detail=(
                    f"Input tokens went from {llms[0].tokens_in} to {llms[-1].tokens_in} "
                    f"across {len(llms)} LLM calls. This run was heading for the context "
                    f"limit; cost per step was compounding."
                ),
                evidence=[s.span_id for s in llms],
                wasted_tokens=wasted,
                suggestion="Summarize older tool outputs instead of carrying full history forward.",
            )
    return None


def detect_premature_answer(trace) -> Finding | None:
    """Agent answered without touching any available tool."""
    tools = trace.tool_spans()
    if tools or not trace.tools:
        return None
    root = next((s for s in trace.spans if s.kind == "agent"), None)
    answer = (root.output if root else "") or ""
    severity = "high" if trace.status == "failed" else "medium"
    return Finding(
        mode="premature_answer",
        severity=severity,
        title="Premature answer: responded without using any tool",
        detail=(
            f"The agent had tools available {trace.tools} but answered directly from "
            f"its own weights: '{str(answer)[:120]}'. This is where confident-sounding "
            f"hallucinations come from."
        ),
        evidence=[root.span_id] if root else [],
        wasted_tokens=0,
        suggestion=(
            "Require at least one grounding tool call before answering factual questions, "
            "or route factual queries to a retrieval-first path."
        ),
    )


def detect_hallucinated_tool(trace) -> Finding | None:
    """Agent tried to call a tool that does not exist."""
    declared = set(trace.tools or [])
    if not declared:
        return None
    bad = [s for s in trace.tool_spans() if s.name not in declared]
    if not bad:
        return None
    return Finding(
        mode="hallucinated_tool",
        severity="high",
        title=f"Hallucinated tool call: '{bad[0].name}' does not exist",
        detail=(
            f"The agent invented a tool '{bad[0].name}'. Declared tools are {sorted(declared)}. "
            f"This usually means the tool descriptions are vague or the model is too small "
            f"for the tool count."
        ),
        evidence=[s.span_id for s in bad],
        wasted_tokens=sum(s.tokens for s in bad),
        suggestion=(
            "Validate tool names against the registry before execution, and return the "
            "error to the planner as 'unknown tool, pick from this list' so it recovers."
        ),
    )


def detect_planning_thrash(trace) -> Finding | None:
    """Many LLM calls in a row with no tool action: the agent thinks but never acts."""
    ordered = [s for s in trace.ordered_spans() if s.kind in ("llm", "tool")]
    longest, current = [], []
    for s in ordered:
        if s.kind == "llm":
            current.append(s)
        else:
            longest = max(longest, current, key=len)
            current = []
    longest = max(longest, current, key=len)
    if len(longest) >= 4:
        return Finding(
            mode="planning_thrash",
            severity="medium",
            title=f"Planning thrash: {len(longest)} LLM calls with no tool action between them",
            detail=(
                "The agent kept 'thinking' without doing anything. Usually a sign the "
                "planner prompt is too open-ended, or every tool looks equally bad so it "
                "stalls instead of committing."
            ),
            evidence=[s.span_id for s in longest],
            wasted_tokens=sum(s.tokens for s in longest[1:]),
            suggestion=(
                "Force action: if 3 consecutive LLM steps produce no tool call, inject a "
                "nudge like 'pick your best tool and act now'."
            ),
        )
    return None


def detect_slow_bleed(trace) -> Finding | None:
    """Run succeeded but took far too many steps: death by a thousand calls."""
    steps = [s for s in trace.ordered_spans() if s.kind in ("llm", "tool")]
    if len(steps) <= 20:
        return None
    excess = steps[12:]
    return Finding(
        mode="slow_bleed",
        severity="medium",
        title=f"Slow bleed: {len(steps)} steps for a task that should take ~10",
        detail=(
            f"This run {'failed' if trace.status == 'failed' else 'succeeded'} after "
            f"{len(steps)} steps. Even when agents eventually get there, step bloat is "
            f"latency and money: {trace.total_tokens:,} tokens on one query."
        ),
        evidence=[s.span_id for s in excess],
        wasted_tokens=sum(s.tokens for s in excess),
        suggestion=(
            "Set a step budget with a graceful degradation path: after N steps, "
            "summarize progress and ask the user what to prioritize."
        ),
    )


DETECTORS = [
    detect_tool_loop,
    detect_error_cascade,
    detect_context_bloat,
    detect_premature_answer,
    detect_hallucinated_tool,
    detect_planning_thrash,
    detect_slow_bleed,
]


def mode_counts(findings) -> Counter:
    return Counter(f.mode for f in findings)
