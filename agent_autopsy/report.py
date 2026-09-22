"""Markdown incident reports: the output you paste into the postmortem doc."""
from __future__ import annotations


def _excerpt(value, limit=140) -> str:
    text = str(value) if value is not None else ""
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


def render_trace_report(autopsy, trace) -> str:
    lines = [
        f"# Autopsy: {autopsy.trace_id}",
        "",
        f"Agent `{autopsy.agent}` ({autopsy.version}) — verdict: **{autopsy.verdict.upper()}**",
        f"Steps: {autopsy.n_steps} · Tokens: {autopsy.total_tokens:,} · "
        f"Wasted: {autopsy.wasted_tokens:,} · Duration: {autopsy.duration_ms / 1000:.1f}s",
        "",
    ]
    if autopsy.root_cause:
        lines += [f"**Probable root cause:** {autopsy.root_cause.title}", ""]
    if not autopsy.findings:
        lines.append("No failure patterns detected. This run looks healthy.")
        return "\n".join(lines)

    lines.append("## Findings")
    for i, f in enumerate(autopsy.findings, 1):
        lines += [
            "",
            f"### {i}. [{f.severity.upper()}] {f.title}",
            "",
            f.mode.replace("_", " ").title() + f" · ~{f.wasted_tokens:,} tokens wasted",
            "",
            f.detail,
            "",
            "**Evidence:**",
        ]
        for span_id in f.evidence[:6]:
            span = trace.span_by_id(span_id)
            if not span:
                continue
            shown = _excerpt(span.error or span.input or span.output)
            lines.append(f"- `{span.kind}:{span.name}` ({span.duration_ms / 1000:.1f}s) — {shown}")
        if len(f.evidence) > 6:
            lines.append(f"- ...and {len(f.evidence) - 6} more spans")
        lines += ["", f"**Fix:** {f.suggestion}"]
    return "\n".join(lines)


def render_fleet_report(report) -> str:
    lines = [
        "# Fleet Autopsy Report",
        "",
        f"Agents: {', '.join(report.agents)} · Traces: {report.n_traces}",
        f"Failure rate: {report.failure_rate:.1%} · "
        f"Wasted tokens: {report.total_wasted_tokens:,} / {report.total_tokens:,} "
        f"({report.waste_rate:.1%})",
        "",
        "## Failure modes",
        "",
    ]
    if not report.by_mode:
        lines.append("No failure patterns detected across the fleet.")
    else:
        for mode, count in report.by_mode.most_common():
            lines.append(f"- **{mode}**: {count} traces ({count / report.n_traces:.0%} of fleet)")
    lines += ["", "## Tools most involved in failures", ""]
    if not report.by_tool:
        lines.append("None.")
    else:
        for tool, count in report.by_tool.most_common(10):
            lines.append(f"- `{tool}`: {count} failure involvements")
    lines += ["", "## Most wasteful traces", ""]
    for trace_id, wasted, modes in report.worst_traces:
        if wasted == 0:
            continue
        lines.append(f"- `{trace_id}`: {wasted:,} wasted tokens ({', '.join(modes)})")
    return "\n".join(lines)
