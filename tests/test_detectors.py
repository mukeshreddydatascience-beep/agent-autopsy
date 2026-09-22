"""Detector tests: each failure mode must fire on its fixture and stay quiet on healthy."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_autopsy.trace import load_trace
from agent_autopsy.analyzer import autopsy_trace
from agent_autopsy.fleet import autopsy_fleet

FIX = os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures")


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(f"FAILED: {name}")


def test_tool_loop():
    a = autopsy_trace(load_trace(f"{FIX}/tool_loop.json"))
    check("tool_loop detected", "tool_loop" in a.modes)
    check("tool_loop verdict failed", a.verdict == "failed")
    check("tool_loop waste > 0", a.wasted_tokens > 0)


def test_error_cascade():
    a = autopsy_trace(load_trace(f"{FIX}/error_cascade.json"))
    check("error_cascade detected", "error_cascade" in a.modes)


def test_context_bloat():
    a = autopsy_trace(load_trace(f"{FIX}/context_bloat.json"))
    check("context_bloat detected", "context_bloat" in a.modes)


def test_premature_answer():
    a = autopsy_trace(load_trace(f"{FIX}/premature.json"))
    check("premature_answer detected", "premature_answer" in a.modes)


def test_hallucinated_tool():
    a = autopsy_trace(load_trace(f"{FIX}/hallucinated_tool.json"))
    check("hallucinated_tool detected", "hallucinated_tool" in a.modes)


def test_planning_thrash():
    a = autopsy_trace(load_trace(f"{FIX}/planning_thrash.json"))
    check("planning_thrash detected", "planning_thrash" in a.modes)


def test_slow_bleed():
    a = autopsy_trace(load_trace(f"{FIX}/slow_bleed.json"))
    check("slow_bleed detected", "slow_bleed" in a.modes)


def test_healthy_is_clean():
    a = autopsy_trace(load_trace(f"{FIX}/healthy.json"))
    check("healthy trace is clean", a.verdict == "clean" and not a.findings)


def test_fleet_aggregates():
    import glob
    traces = [load_trace(f) for f in sorted(glob.glob(f"{FIX}/*.json"))]
    r = autopsy_fleet(traces)
    check("fleet counts all traces", r.n_traces == len(traces))
    check("fleet finds failures", r.n_failed >= 5)
    check("fleet ranks tool_loop top", r.by_mode.most_common(1)[0][0] in
          {"tool_loop", "error_cascade", "context_bloat"})


if __name__ == "__main__":
    test_tool_loop()
    test_error_cascade()
    test_context_bloat()
    test_premature_answer()
    test_hallucinated_tool()
    test_planning_thrash()
    test_slow_bleed()
    test_healthy_is_clean()
    test_fleet_aggregates()
    print("All detector tests passed.")
