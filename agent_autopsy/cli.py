"""agent-autopsy: postmortems for agent runs."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from .trace import load_trace
from .analyzer import autopsy_trace
from .fleet import autopsy_fleet
from .report import render_trace_report, render_fleet_report
from .importers import IMPORTERS


def cmd_trace(args) -> int:
    trace = load_trace(args.file)
    result = autopsy_trace(trace)
    if args.format == "md":
        print(render_trace_report(result, trace))
    else:
        print(f"trace: {result.trace_id}  verdict: {result.verdict}")
        print(f"steps: {result.n_steps}  tokens: {result.total_tokens:,}  "
              f"wasted: {result.wasted_tokens:,}")
        for f in result.findings:
            print(f"  [{f.severity}] {f.mode}: {f.title}")
            print(f"    fix: {f.suggestion}")
    if args.fail_on_failure and result.verdict == "failed":
        return 1
    return 0


def cmd_fleet(args) -> int:
    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        print(f"No trace files found in {args.dir}", file=sys.stderr)
        return 2
    traces = [load_trace(f) for f in files]
    report = autopsy_fleet(traces)
    text = render_fleet_report(report)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"Wrote {args.out}")
    else:
        print(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agent-autopsy",
                                description="Postmortems for agent runs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trace", help="Autopsy a single trace file")
    t.add_argument("file", help="Trace JSON file")
    t.add_argument("--format", choices=["text", "md"], default="text")
    t.add_argument("--fail-on-failure", action="store_true",
                   help="Exit 1 when the verdict is 'failed' (CI gate)")

    f = sub.add_parser("fleet", help="Aggregate autopsies across many traces")
    f.add_argument("dir", help="Directory of trace JSON files")
    f.add_argument("--out", help="Write markdown report to this file")

    im = sub.add_parser("import", help="Convert a LangSmith/Langfuse export to a trace")
    im.add_argument("--from", dest="source", choices=["langsmith", "langfuse"],
                    required=True)
    im.add_argument("--in", dest="in_file", required=True, help="Export JSON file")
    im.add_argument("--out", dest="out_file", required=True, help="Trace JSON file")
    im.add_argument("--status", choices=["ok", "failed"],
                    help="Override auto-detected status")

    args = p.parse_args(argv)
    if args.cmd == "trace":
        return cmd_trace(args)
    if args.cmd == "fleet":
        return cmd_fleet(args)
    return cmd_import(args)


def cmd_import(args) -> int:
    with open(args.in_file) as f:
        raw = json.load(f)
    trace = IMPORTERS[args.source](raw, status=args.status)
    payload = {
        "trace_id": trace.trace_id, "agent": trace.agent, "version": trace.version,
        "status": trace.status, "tools": trace.tools,
        "spans": [
            {"span_id": s.span_id, "parent_id": s.parent_id, "name": s.name,
             "kind": s.kind, "start_ms": s.start_ms, "end_ms": s.end_ms,
             "input": s.input, "output": s.output, "error": s.error,
             "tokens_in": s.tokens_in, "tokens_out": s.tokens_out}
            for s in trace.spans
        ],
    }
    with open(args.out_file, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"Converted {args.source} export -> {args.out_file} "
          f"({len(trace.spans)} spans, status={trace.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
