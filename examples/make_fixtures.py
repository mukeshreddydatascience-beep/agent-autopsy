"""Generate realistic failing (and healthy) agent traces for demos and tests.

Run: python examples/make_fixtures.py
Writes JSON fixtures to examples/fixtures/.
"""
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "fixtures")


class Clock:
    def __init__(self):
        self.t = 0.0

    def step(self, ms):
        self.t += ms
        return self.t


def span(clock, sid, name, kind, ms, parent="agent_run", input=None, output=None,
         error=None, ti=0, to=0):
    start = clock.t
    clock.step(ms)
    return {
        "span_id": sid, "parent_id": parent, "name": name, "kind": kind,
        "start_ms": start, "end_ms": clock.t,
        "input": input, "output": output, "error": error,
        "tokens_in": ti, "tokens_out": to,
    }


def root(clock, ms, output=None, status_note=""):
    return {
        "span_id": "agent_run", "parent_id": None, "name": "support-bot",
        "kind": "agent", "start_ms": 0, "end_ms": ms,
        "input": "Where is my order #48291?",
        "output": output, "error": None,
        "tokens_in": 0, "tokens_out": 0,
    }


def llm(clock, sid, ms, ti, to, out="..."):
    return span(clock, sid, "planner", "llm", ms, input="[conversation history]",
                output=out, ti=ti, to=to)


def tool(clock, sid, name, args, ms, out="ok", error=None, ti=120, to=80):
    return span(clock, sid, name, "tool", ms, input=args, output=out,
                error=error, ti=ti, to=to)


def save(name, trace_id, status, tools, spans, total_ms):
    trace = {"trace_id": trace_id, "agent": "support-bot", "version": "v3",
             "status": status, "tools": tools,
             "spans": [root(CL, total_ms,
                            output="done" if status == "ok" else None)] + spans}
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(trace, f, indent=2)


TOOLS = ["search_docs", "get_order", "issue_refund"]
CL = Clock()


def healthy():
    global CL
    CL = Clock()
    spans = [
        llm(CL, "l1", 900, 1500, 120, out="need order status -> get_order"),
        tool(CL, "t1", "get_order", {"order_id": "48291"}, 400,
             out="{'status': 'shipped', 'eta': 'Sep 25'}"),
        llm(CL, "l2", 800, 1900, 150, out="final answer"),
    ]
    save("healthy.json", "t-healthy-1", "ok", TOOLS, spans, CL.t)


def tool_loop():
    global CL
    CL = Clock()
    spans = [llm(CL, "l1", 900, 1500, 120, out="search docs")]
    for i in range(4):
        spans.append(tool(CL, f"t{i}", "search_docs",
                           {"query": "refund policy electronics"},
                           500, out="{'hits': []}"))
        spans.append(llm(CL, f"l{i + 2}", 800, 1800 + i * 200, 100,
                         out="no hits, search again"))
    save("tool_loop.json", "t-loop-1", "failed", TOOLS, spans, CL.t)


def error_cascade():
    global CL
    CL = Clock()
    spans = [
        llm(CL, "l1", 900, 1500, 120, out="get order"),
        tool(CL, "t1", "get_order", {"order_id": "XYZ"}, 300,
             error="OrderNotFound: no order 'XYZ'", ti=120, to=40),
        llm(CL, "l2", 800, 1900, 110, out="retry get_order"),
        tool(CL, "t2", "get_order", {"order_id": "XYZ"}, 300,
             error="OrderNotFound: no order 'XYZ'", ti=120, to=40),
        llm(CL, "l3", 800, 2200, 130, out="ask user to verify id"),
    ]
    save("error_cascade.json", "t-cascade-1", "failed", TOOLS, spans, CL.t)


def context_bloat():
    global CL
    CL = Clock()
    ti = 2000
    spans = []
    for i in range(5):
        spans.append(tool(CL, f"t{i}", "search_docs", {"query": f"q{i}"}, 400,
                           out="long doc chunk " * 50))
        spans.append(llm(CL, f"l{i}", 900, ti, 150, out="keep reading"))
        ti = int(ti * 2.2)
    spans.append(span(CL, "l5", "planner", "llm", 900, input="[huge history]",
                      output=None, error="context_length_exceeded: 131072 limit",
                      ti=140000, to=0))
    save("context_bloat.json", "t-bloat-1", "failed", TOOLS, spans, CL.t)


def premature_answer():
    global CL
    CL = Clock()
    spans = [llm(CL, "l1", 900, 1500, 200,
                 out="Your order shipped yesterday, arriving Sep 25.")]
    save("premature.json", "t-premature-1", "failed", TOOLS, spans, CL.t)


def hallucinated_tool():
    global CL
    CL = Clock()
    spans = [
        llm(CL, "l1", 900, 1500, 120, out="need admin access"),
        tool(CL, "t1", "delete_user", {"user": "u_991"}, 200,
             error="UnknownTool: delete_user not registered", ti=100, to=30),
        llm(CL, "l2", 800, 1800, 100, out="confused"),
    ]
    save("hallucinated_tool.json", "t-halluc-1", "failed", TOOLS, spans, CL.t)


def planning_thrash():
    global CL
    CL = Clock()
    spans = [llm(CL, f"l{i}", 900, 1500 + i * 300, 200,
                 out=f"considering option {i}") for i in range(5)]
    spans.append(tool(CL, "t1", "get_order", {"order_id": "48291"}, 400,
                      out="{'status': 'shipped'}"))
    save("planning_thrash.json", "t-thrash-1", "ok", TOOLS, spans, CL.t)


def slow_bleed():
    global CL
    CL = Clock()
    spans = []
    for i in range(14):
        spans.append(llm(CL, f"l{i}", 700, 1500 + i * 100, 120, out="step"))
        spans.append(tool(CL, f"t{i}", "search_docs", {"query": f"variant {i}"},
                           350, out="{'hits': ['doc']}"))
    spans.append(llm(CL, "lf", 800, 3200, 200, out="final answer"))
    save("slow_bleed.json", "t-bleed-1", "ok", TOOLS, spans, CL.t)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    healthy()
    tool_loop()
    error_cascade()
    context_bloat()
    premature_answer()
    hallucinated_tool()
    planning_thrash()
    slow_bleed()
    print(f"Wrote {len(os.listdir(OUT))} fixtures to {OUT}/")
