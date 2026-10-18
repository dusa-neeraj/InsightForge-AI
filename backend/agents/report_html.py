import base64
import html
from typing import Any

from agents.report_charts import render_chart

CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1e293b;max-width:900px;
margin:0 auto;padding:32px;line-height:1.55}
h1{font-size:30px;margin:0}
h2{font-size:20px;margin:40px 0 12px;border-bottom:2px solid #e0e7ff;padding-bottom:6px}
h3{font-size:15px;margin:18px 0 6px}
.muted{color:#64748b;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.card{border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px}
.card b{display:block;font-size:22px;margin:2px 0}
.card span{font-size:12px;color:#64748b}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
th{background:#4f46e5;color:#fff;text-align:left;padding:6px 8px}
td{border-bottom:1px solid #e2e8f0;padding:6px 8px;vertical-align:top}
.tag{display:inline-block;border-radius:999px;padding:1px 8px;font-size:11px;font-weight:600}
.high{background:#fee2e2;color:#b91c1c}.medium{background:#fef3c7;color:#b45309}.low{background:#f1f5f9;color:#475569}
.info{background:#e0f2fe;color:#0369a1}
figure{margin:18px 0;page-break-inside:avoid}
figure img{max-width:100%;border:1px solid #e2e8f0;border-radius:8px}
figcaption{font-size:12px;color:#64748b}
ul{padding-left:20px}
.note{background:#f8fafc;border-left:4px solid #4f46e5;padding:10px 14px;margin:12px 0}
@media print{body{padding:0;max-width:none}h2{page-break-after:avoid}.card,tr{page-break-inside:avoid}}
"""
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _tag(level: str) -> str:
    return f'<span class="tag {esc(level)}">{esc(level.upper())}</span>'


def _chart_figure(chart: dict[str, Any]) -> str:
    svg = render_chart(chart, "svg")
    if svg is None:
        return ""
    source = base64.b64encode(svg).decode("ascii")
    return (
        f'<figure><img alt="{esc(chart["title"])}" src="data:image/svg+xml;base64,{source}">'
        f'<figcaption>Why this chart: {esc(chart["reason"])}</figcaption></figure>'
    )


def render_html(data: dict[str, Any]) -> str:
    ov, q, narration = data["overview"], data["quality"], data["narration"]
    parts: list[str] = []
    add = parts.append

    add("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    add(f'<meta http-equiv="Content-Security-Policy" content="{CSP}">')
    add(f"<title>{esc(data['title'])} - Data Analysis Report</title><style>{CSS}</style></head><body>")
    add(f"<h1>Data Analysis Report</h1>")
    add(f"<p class=\"muted\">Dataset: <b>{esc(data['title'])}</b> · Generated {esc(data['generated_at'])}</p>")

    # overview
    cards = [
        ("Rows", f"{ov['rows']:,}", "after cleaning"),
        ("Columns", f"{ov['columns']:,}", f"{ov['numeric']} number · {ov['categorical']} text · {ov['date']} date"),
        ("Missing cells", f"{ov['missing_pct']}%", "after cleaning"),
        ("Quality score", f"{q['after']['score']}/100", q["after"]["grade"]),
    ]
    add('<div class="grid">' + "".join(
        f'<div class="card"><span>{esc(label)}</span><b>{esc(value)}</b><span>{esc(hint)}</span></div>'
        for label, value, hint in cards) + "</div>")
    if ov["date_range"]:
        add(f'<p class="muted">Dates covered: {esc(ov["date_range"])}</p>')

    # key findings
    add("<h2>Key findings</h2>")
    source = f"AI-written ({esc(narration.get('model'))})" if narration.get("source") == "ai" else "Rule-based"
    add(f'<div class="note"><b>Summary</b> <span class="muted">· {source}</span><br>{esc(narration["summary"])}</div>')
    add("<ul>" + "".join(
        f"<li>{_tag(item['importance'])} {esc(item['message'])}</li>" for item in data["key_findings"]) + "</ul>")
    if narration.get("recommendations"):
        add("<h3>Suggested next steps</h3><ul>" + "".join(
            f"<li>{esc(text)}</li>" for text in narration["recommendations"]) + "</ul>")

    # KPIs
    add("<h2>Key numbers</h2>")
    add('<div class="grid">' + "".join(
        f'<div class="card"><span>{esc(k["label"])}</span><b>{esc(k["value"])}</b><span>{esc(k["subtitle"])}</span></div>'
        for k in data["kpis"]) + "</div>")

    # quality
    add("<h2>Data quality</h2>")
    add(_table(["", "Before cleaning", "After cleaning"], [
        ["Quality score", f"{q['before']['score']} ({q['before']['grade']})", f"{q['after']['score']} ({q['after']['grade']})"],
        ["Rows", f"{q['before']['rows']:,}", f"{q['after']['rows']:,}"],
        ["Duplicate rows", q["before"]["duplicate_rows"], q["after"]["duplicate_rows"]],
        ["Missing cells", q["before"]["missing_cells"], q["after"]["missing_cells"]],
        ["Outlier cells", q["before"]["outlier_cells"], q["after"]["outlier_cells"]],
    ]))
    if q["issues"]:
        add("<h3>Remaining issues</h3><ul>" + "".join(
            f"<li>{_tag(i['severity'])} {esc(i['message'])}</li>" for i in q["issues"][:10]) + "</ul>")
    else:
        add("<p>No issues found.</p>")

    # cleaning
    add("<h2>Cleaning steps</h2><ol>" + "".join(
        f"<li>{esc(c['message'])}</li>" for c in data["changes"]) + "</ol>")
    add('<p class="muted">Outliers are flagged, never deleted.</p>')

    # statistics
    add("<h2>Statistics</h2>")
    if data["numeric_stats"]["rows"]:
        add("<h3>Number columns</h3>" + _table(data["numeric_stats"]["headers"], data["numeric_stats"]["rows"]))
    if data["category_stats"]["rows"]:
        add("<h3>Text columns</h3>" + _table(data["category_stats"]["headers"], data["category_stats"]["rows"]))

    # charts
    figures = [_chart_figure(chart) for chart in data["charts"]]
    figures = [f for f in figures if f]
    add("<h2>Charts</h2>")
    add("".join(figures) if figures else "<p>No charts were generated for this dataset.</p>")

    # all insights
    add("<h2>All insights</h2>")
    add(_table(["ID", "Importance", "Insight"],
               [[i["id"], i["importance"], i["message"]] for i in data["insights"]]))

    add('<p class="muted" style="margin-top:40px">Generated by AI Data Analyst Agent. All numbers are '
        "calculated from the data. Text labeled AI-written was produced by a language model and checked "
        "against those numbers.</p></body></html>")
    return "".join(parts)