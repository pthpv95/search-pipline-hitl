"""Generate a nicely formatted PDF report from a saved eval run JSON."""

from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path

from fpdf import FPDF


_FONT = "Dejavu"


class ReportPDF(FPDF):
    """Custom PDF with header/footer for research reports."""

    def __init__(self, title: str, topic: str):
        super().__init__()
        self._report_title = title
        self._topic = topic
        # Register Arial as a Unicode-capable font
        _fdir = "/System/Library/Fonts/Supplemental/"
        self.add_font("Dejavu", "", _fdir + "Arial.ttf")
        self.add_font("Dejavu", "B", _fdir + "Arial Bold.ttf")
        self.add_font("Dejavu", "I", _fdir + "Arial Italic.ttf")
        self.add_font("Dejavu", "BI", _fdir + "Arial Bold Italic.ttf")

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(_FONT, "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, self._topic, align="L")
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font(_FONT, "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def build_pdf(run_path: Path, output_path: Path | None = None) -> Path:
    data = json.loads(run_path.read_text())
    report = data["final_report"]
    title = report["title"]
    topic = data["topic"]
    body = report["body"]
    sources = report.get("sources", [])
    exec_summary = report.get("executive_summary", "")
    limitations = data.get("limitations", [])
    token_usage = data.get("token_usage", {})
    node_timings = data.get("node_timings", {})
    metadata = data.get("run_metadata", {})

    pdf = ReportPDF(title, topic)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # --- Cover page ---
    pdf.add_page()
    pdf.ln(50)
    # Title
    pdf.set_font(_FONT, "B", 22)
    pdf.set_text_color(25, 25, 112)  # midnight blue
    pdf.multi_cell(0, 12, title, align="C")
    pdf.ln(8)
    # Subtitle line
    pdf.set_font(_FONT, "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Research Report  |  {data.get('saved_at', '')[:8]}", align="C")
    pdf.ln(6)
    pdf.cell(0, 8, f"Model: {metadata.get('model_name', 'N/A')}  |  Mode: {data.get('mode', 'N/A')}", align="C")
    pdf.ln(20)

    # Accent line
    pdf.set_draw_color(25, 25, 112)
    pdf.set_line_width(0.8)
    x_start = 60
    pdf.line(x_start, pdf.get_y(), 210 - x_start, pdf.get_y())
    pdf.ln(12)

    # Executive summary on cover
    if exec_summary:
        pdf.set_font(_FONT, "B", 12)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 8, "Executive Summary")
        pdf.ln(8)
        pdf.set_font(_FONT, "", 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, exec_summary)
        pdf.ln(6)

    # Run stats box
    pdf.set_fill_color(240, 240, 248)
    pdf.set_font(_FONT, "B", 9)
    pdf.set_text_color(60, 60, 60)
    y_box = pdf.get_y()
    pdf.cell(0, 7, "  Run Statistics", fill=True)
    pdf.ln(8)
    pdf.set_font(_FONT, "", 9)
    stats = [
        f"Search loops: {data.get('loop_count', 'N/A')}/{data.get('max_loops', 'N/A')}",
        f"Sources: {len(sources)}",
        f"Word count: {report.get('word_count', 'N/A')}",
        f"Total tokens: {token_usage.get('total', 0):,}",
        f"Total time: {node_timings.get('total', 0):.1f}s",
    ]
    for s in stats:
        pdf.cell(0, 5, f"    {s}", fill=True)
        pdf.ln(5.5)
    pdf.ln(6)

    # --- Body pages ---
    pdf.add_page()

    # Parse markdown body into sections
    lines = body.split("\n")
    for line in lines:
        line = line.rstrip()

        # Heading 1
        if line.startswith("# "):
            pdf.ln(4)
            pdf.set_font(_FONT, "B", 16)
            pdf.set_text_color(25, 25, 112)
            pdf.multi_cell(0, 9, line[2:])
            pdf.ln(3)
            # Accent line under H1
            pdf.set_draw_color(25, 25, 112)
            pdf.set_line_width(0.5)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)
            continue

        # Heading 2
        if line.startswith("## "):
            pdf.ln(6)
            pdf.set_font(_FONT, "B", 13)
            pdf.set_text_color(40, 60, 120)
            pdf.multi_cell(0, 8, line[3:])
            pdf.ln(2)
            continue

        # Heading 3
        if line.startswith("### "):
            pdf.ln(4)
            pdf.set_font(_FONT, "BI", 11)
            pdf.set_text_color(60, 80, 140)
            pdf.multi_cell(0, 7, line[4:])
            pdf.ln(2)
            continue

        # Empty line
        if not line.strip():
            pdf.ln(3)
            continue

        # Body paragraph — render with bold spans for **text**
        pdf.set_font(_FONT, "", 10)
        pdf.set_text_color(40, 40, 40)
        _render_rich_line(pdf, line)
        pdf.ln(2)

    # --- Sources page ---
    pdf.add_page()
    pdf.set_font(_FONT, "B", 14)
    pdf.set_text_color(25, 25, 112)
    pdf.cell(0, 10, "Sources")
    pdf.ln(10)
    pdf.set_draw_color(25, 25, 112)
    pdf.set_line_width(0.4)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    for i, src in enumerate(sources, 1):
        pdf.set_font(_FONT, "B", 9)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(8, 5, f"[{i}]")
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(40, 40, 40)
        title_text = src.get("title", "Untitled")
        pdf.multi_cell(0, 5, title_text)
        pdf.set_font(_FONT, "", 8)
        pdf.set_text_color(80, 80, 180)
        pdf.set_x(pdf.l_margin + 8)
        pdf.multi_cell(0, 4, src.get("url", ""))
        if src.get("snippet"):
            pdf.set_font(_FONT, "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.set_x(pdf.l_margin + 8)
            snippet = src["snippet"][:200] + ("..." if len(src["snippet"]) > 200 else "")
            pdf.multi_cell(0, 4, snippet)
        pdf.ln(4)

    # --- Limitations ---
    if limitations:
        pdf.ln(6)
        pdf.set_font(_FONT, "B", 12)
        pdf.set_text_color(25, 25, 112)
        pdf.cell(0, 8, "Known Limitations")
        pdf.ln(8)
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(60, 60, 60)
        for lim in limitations:
            pdf.cell(6, 5, chr(8226))  # bullet
            pdf.multi_cell(0, 5, f" {lim}")
            pdf.ln(2)

    # Save
    if output_path is None:
        output_path = run_path.with_suffix(".pdf")
    pdf.output(str(output_path))
    return output_path


def _render_rich_line(pdf: FPDF, text: str):
    """Render a line with **bold** and [N] citation markers."""
    parts = re.split(r"(\*\*.*?\*\*|\[\d+\])", text)
    x_start = pdf.get_x()
    line_w = pdf.w - pdf.l_margin - pdf.r_margin

    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            pdf.set_font(_FONT, "B", 10)
            pdf.write(5.5, part[2:-2])
            pdf.set_font(_FONT, "", 10)
        elif re.match(r"^\[\d+\]$", part):
            pdf.set_font(_FONT, "B", 8)
            pdf.set_text_color(80, 80, 180)
            pdf.write(5.5, part)
            pdf.set_font(_FONT, "", 10)
            pdf.set_text_color(40, 40, 40)
        else:
            pdf.write(5.5, part)
    pdf.ln(5.5)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_report_pdf.py <run.json> [output.pdf]")
        sys.exit(1)
    run_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    result = build_pdf(run_path, out_path)
    print(f"PDF saved: {result}")
