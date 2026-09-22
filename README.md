# Agent Autopsy

Postmortems for agent runs. When your agent fails in production, this tells
you *why* not just that it did.

## The problem

Agents fail in ways that are painful to debug. You get a giant trace, a
confused support ticket, and no answer to the only question that matters:
what went wrong?

I kept seeing the same failure shapes over and over: the agent calling the
same tool five times with the same arguments, retrying a tool that will
never succeed, filling up its context window until the output turns to
garbage, answering from its own weights without touching any tool. So I
codified the patterns. Now the trace gets an autopsy.

## What it does

**Single-trace autopsy.** Feed it one execution trace. It runs seven
failure-mode detectors, ranks what it finds, shows the evidence spans, and
suggests the fix:

```
trace: t-loop-1  verdict: failed
steps: 9  tokens: 11,220  wasted: 600
  [high] tool_loop: Tool loop: 'search_docs' called 4x with identical arguments
    fix: Add a repeat-call circuit breaker (max 2 identical calls), and make
    the planner react to 'search_docs' returning the same result twice by
    changing strategy instead of retrying.
```

**Fleet analysis.** One trace tells you what broke; a hundred traces tell
you *what's broken*. Point it at a directory of traces and get the patterns:

```
Failure rate: 62.5% · Wasted tokens: 265,727 / 302,377 (87.9%)

## Failure modes
- **tool_loop**: 18 traces (22% of fleet)
- **error_cascade**: 11 traces (13% of fleet)

## Tools most involved in failures
- `search_docs`: 34 failure involvements
```

That second output is the one you bring to the planning meeting. It turns
"agents feel flaky" into "22% of our failures are tool loops, mostly in
search_docs, burning 87% of our token budget."

## The seven failure modes

| Mode | What it catches |
|---|---|
| `tool_loop` | Same tool, same arguments, 3+ times. The agent is stuck. |
| `error_cascade` | Tool errors, agent retries with the same bad input. Pure burn. |
| `context_bloat` | Context limit hit, or prompt size exploding mid-run. |
| `premature_answer` | Answered without using any available tool. Hallucination territory. |
| `hallucinated_tool` | Called a tool that doesn't exist. |
| `planning_thrash` | 4+ LLM calls in a row, no action. Thinking without doing. |
| `slow_bleed` | Eventually worked but took 20+ steps. Latency and money. |

Every finding carries its evidence (the exact spans), an estimate of wasted
tokens, and a concrete fix. No black boxes.

## Quickstart

```bash
pip install -r requirements.txt

# Autopsy one trace
python -m agent_autopsy.cli trace my_trace.json

# Markdown incident report (paste it into the postmortem doc)
python -m agent_autopsy.cli trace my_trace.json --format md

# Fleet analysis across many traces
python -m agent_autopsy.cli fleet ./traces/ --out fleet_report.md

# Fail CI when a trace verdict is 'failed'
python -m agent_autopsy.cli trace my_trace.json --fail-on-failure
```

## Bring your own traces

The core reads plain JSON so it never locks you to a vendor. If you already
trace with LangSmith or Langfuse, convert the export first:

```bash
# LangSmith run export (API response or downloaded JSON)
python -m agent_autopsy.cli import --from langsmith \
    --in langsmith_run.json --out trace.json

# Langfuse trace export (with observations)
python -m agent_autopsy.cli import --from langfuse \
    --in langfuse_trace.json --out trace.json

python -m agent_autopsy.cli trace trace.json
```

Status is auto-detected (any errored span means failed); override with
`--status ok` when you know better.

## Trace format

Plain JSON. Bring your own traces from LangSmith, Langfuse, or your own
instrumentation — anything you can convert to this shape:

```json
{
  "trace_id": "t-001",
  "agent": "support-bot",
  "version": "v3",
  "status": "failed",
  "tools": ["search_docs", "get_order"],
  "spans": [
    {"span_id": "s1", "parent_id": null, "name": "support-bot", "kind": "agent",
     "start_ms": 0, "end_ms": 12000, "input": "Where is my order?",
     "output": null, "error": null, "tokens_in": 0, "tokens_out": 0},
    {"span_id": "s2", "parent_id": "s1", "name": "search_docs", "kind": "tool",
     "start_ms": 900, "end_ms": 1400, "input": {"query": "refund policy"},
     "output": "{'hits': []}", "error": null, "tokens_in": 120, "tokens_out": 80}
  ]
}
```

Span kinds are `agent`, `llm`, and `tool`. The detectors only need names,
kinds, inputs, errors, and token counts.

## Try it

The repo ships with realistic fixtures covering every failure mode:

```bash
python examples/make_fixtures.py
python -m agent_autopsy.cli fleet examples/fixtures/
```

## Why this, why now

Evals tell you *whether* quality dropped. This tells you *why the agent
died*. If you're running agents in production, you need both: one guards
the releases, the other explains the incidents. That's the whole
reliability story.

## License

MIT. Use it, fork it, run it on your own traces.
