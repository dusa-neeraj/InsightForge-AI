import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.report_charts import render_chart


WIDTH = 170 * mm
INDIGO = colors.HexColor("#4f46e5")
LINE = colors.HexColor("#e2e8f0")


def _t(value: Any) -> str:
    """Text for a PDF paragraph: escaped, and limited to what the built-in font can draw."""
    text = str(value).replace("₹", "Rs ")
    return escape(text.encode("cp1252", "replace").decode("cp1252"))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    body = ParagraphStyle(
        "body",
        parent=base["BodyText"],
        fontSize=9.5,
        leading=13,
    )

    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            alignment=0,
            fontSize=24,
            leading=28,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=15,
            spaceBefore=16,
            spaceAfter=6,
            textColor=colors.HexColor("#1e293b"),
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": body,
        "small": ParagraphStyle(
            "small",
            parent=body,
            fontSize=8.5,
            leading=11,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=body,
            fontSize=8.5,
            textColor=colors.HexColor("#64748b"),
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=body,
            leftIndent=12,
            bulletIndent=2,
        ),
        "head": ParagraphStyle(
            "head",
            parent=body,
            fontSize=8.5,
            fontName="Helvetica-Bold",
            textColor=colors.white,
        ),
    }


def _table(
    styles: dict[str, ParagraphStyle],
    headers: list,
    rows: list[list],
    widths=None,
) -> Table:
    widths = widths or [WIDTH / len(headers)] * len(headers)

    cell = styles["small"]

    data = [
        [Paragraph(_t(h), styles["head"]) for h in headers]
    ]

    data += [
        [Paragraph(_t(c), cell) for c in row]
        for row in rows
    ]

    table = Table(
        data,
        colWidths=widths,
        repeatRows=1,
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#f8fafc"),
                    ],
                ),
                ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    return table


def _footer(canvas, doc) -> None:
    canvas.saveState()

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#94a3b8"))

    canvas.drawString(
        20 * mm,
        10 * mm,
        "AI Data Analyst Agent",
    )

    canvas.drawRightString(
        190 * mm,
        10 * mm,
        f"Page {doc.page}",
    )

    canvas.restoreState()


def _chart_block(
    styles: dict[str, ParagraphStyle],
    chart: dict[str, Any],
):
    png = render_chart(chart, "png")

    if png is None:
        return None

    pixel_width, pixel_height = ImageReader(
        io.BytesIO(png)
    ).getSize()

    height = min(
        WIDTH * pixel_height / pixel_width,
        120 * mm,
    )

    image = Image(
        io.BytesIO(png),
        width=WIDTH,
        height=height,
    )

    caption = Paragraph(
        _t(f"Why this chart: {chart['reason']}"),
        styles["muted"],
    )

    return KeepTogether(
        [
            image,
            caption,
            Spacer(1, 8),
        ]
    )


def render_pdf(data: dict[str, Any]) -> bytes:
    s = _styles()

    ov = data["overview"]
    q = data["quality"]
    narration = data["narration"]

    story: list = []
    add = story.append

    add(
        Paragraph(
            "Data Analysis Report",
            s["title"],
        )
    )

    add(
        Paragraph(
            _t(
                f"Dataset: {data['title']}  ·  "
                f"Generated {data['generated_at']}"
            ),
            s["muted"],
        )
    )

    add(Spacer(1, 8))

    add(
        _table(
            s,
            ["Measure", "Value"],
            [
                [
                    "Rows (after cleaning)",
                    f"{ov['rows']:,}",
                ],
                [
                    "Columns",
                    f"{ov['columns']} "
                    f"({ov['numeric']} number, "
                    f"{ov['categorical']} text, "
                    f"{ov['date']} date)",
                ],
                [
                    "Missing cells",
                    f"{ov['missing_pct']}%",
                ],
                [
                    "Quality score",
                    f"{q['after']['score']}/100 "
                    f"({q['after']['grade']})",
                ],
                [
                    "Dates covered",
                    ov["date_range"] or "none",
                ],
            ],
            [50 * mm, 120 * mm],
        )
    )

    add(
        Paragraph(
            "Key findings",
            s["h2"],
        )
    )

    label = (
        f"AI-written ({narration.get('model')})"
        if narration.get("source") == "ai"
        else "Rule-based"
    )

    add(
        Paragraph(
            _t(
                f"Summary ({label}): "
                f"{narration['summary']}"
            ),
            s["body"],
        )
    )

    add(Spacer(1, 4))

    for item in data["key_findings"]:
        add(
            Paragraph(
                _t(
                    f"[{item['importance'].upper()}] "
                    f"{item['message']}"
                ),
                s["bullet"],
                bulletText="•",
            )
        )

    if narration.get("recommendations"):
        add(
            Paragraph(
                "Suggested next steps",
                s["h3"],
            )
        )

        for text in narration["recommendations"]:
            add(
                Paragraph(
                    _t(text),
                    s["bullet"],
                    bulletText="-",
                )
            )

    add(
        Paragraph(
            "Key numbers",
            s["h2"],
        )
    )

    add(
        _table(
            s,
            ["KPI", "Value", "Note"],
            [
                [
                    k["label"],
                    k["value"],
                    k["subtitle"],
                ]
                for k in data["kpis"]
            ],
            [55 * mm, 40 * mm, 75 * mm],
        )
    )

    add(
        Paragraph(
            "Data quality",
            s["h2"],
        )
    )

    add(
        _table(
            s,
            [
                "",
                "Before cleaning",
                "After cleaning",
            ],
            [
                [
                    "Quality score",
                    f"{q['before']['score']} "
                    f"({q['before']['grade']})",
                    f"{q['after']['score']} "
                    f"({q['after']['grade']})",
                ],
                [
                    "Rows",
                    f"{q['before']['rows']:,}",
                    f"{q['after']['rows']:,}",
                ],
                [
                    "Duplicate rows",
                    q["before"]["duplicate_rows"],
                    q["after"]["duplicate_rows"],
                ],
                [
                    "Missing cells",
                    q["before"]["missing_cells"],
                    q["after"]["missing_cells"],
                ],
                [
                    "Outlier cells",
                    q["before"]["outlier_cells"],
                    q["after"]["outlier_cells"],
                ],
            ],
            [60 * mm, 55 * mm, 55 * mm],
        )
    )

    if q["issues"]:
        add(
            Paragraph(
                "Remaining issues",
                s["h3"],
            )
        )

        for issue in q["issues"][:10]:
            add(
                Paragraph(
                    _t(
                        f"[{issue['severity'].upper()}] "
                        f"{issue['message']}"
                    ),
                    s["bullet"],
                    bulletText="•",
                )
            )

    add(
        Paragraph(
            "Cleaning steps",
            s["h2"],
        )
    )

    for number, change in enumerate(
        data["changes"],
        start=1,
    ):
        add(
            Paragraph(
                _t(change["message"]),
                s["bullet"],
                bulletText=f"{number}.",
            )
        )

    add(
        Paragraph(
            "Outliers are flagged, never deleted.",
            s["muted"],
        )
    )

    add(
        Paragraph(
            "Statistics",
            s["h2"],
        )
    )

    if data["numeric_stats"]["rows"]:
        add(
            Paragraph(
                "Number columns",
                s["h3"],
            )
        )

        add(
            _table(
                s,
                data["numeric_stats"]["headers"],
                data["numeric_stats"]["rows"],
            )
        )

    if data["category_stats"]["rows"]:
        add(
            Paragraph(
                "Text columns",
                s["h3"],
            )
        )

        add(
            _table(
                s,
                data["category_stats"]["headers"],
                data["category_stats"]["rows"],
            )
        )

    add(
        Paragraph(
            "Charts",
            s["h2"],
        )
    )

    blocks = [
        block
        for block in (
            _chart_block(s, chart)
            for chart in data["charts"]
        )
        if block
    ]

    if blocks:
        story.extend(blocks)
    else:
        add(
            Paragraph(
                "No charts were generated for this dataset.",
                s["body"],
            )
        )

    add(
        Paragraph(
            "All insights",
            s["h2"],
        )
    )

    add(
        _table(
            s,
            ["ID", "Importance", "Insight"],
            [
                [
                    i["id"],
                    i["importance"],
                    i["message"],
                ]
                for i in data["insights"]
            ],
            [15 * mm, 25 * mm, 130 * mm],
        )
    )

    add(Spacer(1, 14))

    add(
        Paragraph(
            "Generated by AI Data Analyst Agent. All numbers are "
            "calculated from the data. Text labeled AI-written was "
            "produced by a language model and checked against those "
            "numbers.",
            s["muted"],
        )
    )

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Data Analysis Report",
    )

    doc.build(
        story,
        onFirstPage=_footer,
        onLaterPages=_footer,
    )

    return buffer.getvalue()