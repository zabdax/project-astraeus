import io
import gc
import copy
import re
import logging
import datetime
from typing import Dict, Any, List

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    # Define a dummy class to prevent NameError
    class DummyCanvas:
        pass
    canvas = type('canvas_dummy', (), {'Canvas': DummyCanvas})

logger = logging.getLogger(__name__)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Draw page number on each page"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        
        # Soft-gray top border for footer
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.5)
        self.line(0.75 * inch, 0.75 * inch, 7.75 * inch, 0.75 * inch)
        
        self.setFont("Times-Roman", 9)
        self.setFillColor(colors.HexColor("#6B7280"))
        
        # Left side: Timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.drawString(0.75 * inch, 0.55 * inch, f"Generated: {timestamp}")
        
        # Right side: Page X of Y
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(7.75 * inch, 0.55 * inch, page_str)
        
        self.restoreState()


def sanitize_text(text: str) -> str:
    """Sanitize text using strict regex mapping for ReportLab core fonts."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    
    replacements = {
        r'[α]': 'alpha', r'[β]': 'beta', r'[γ]': 'gamma', r'[δ]': 'delta',
        r'[θ]': 'theta', r'[σ]': 'sigma', r'[μ]': 'mu', r'[π]': 'pi',
        r'[±]': '+/-', r'[°]': ' deg', r'[≥]': '>=', r'[≤]': '<=',
        r'[×]': 'x', r'[≈]': '~', r'[≠]': '!=',
        r'[—–]': '-', r'[”“]': '"', r'[‘’]': "'"
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    
    # Strict regex to remove any remaining non-ASCII characters (e.g., emojis)
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    return text


def _validate_schema(metrics_payload: Dict[str, Any]):
    """Strict schema validation for metrics_payload"""
    required_root_keys = ["star_id"]
    for key in required_root_keys:
        if key not in metrics_payload:
            raise ValueError(f"Missing required root key in metrics_payload: '{key}'")
            
    if "candidates" not in metrics_payload:
        raise ValueError("Missing 'candidates' array in metrics_payload")
        
    if not isinstance(metrics_payload["candidates"], list):
        raise TypeError("'candidates' must be a list of dictionaries")


def _is_plotly_figure(obj: Any) -> bool:
    """Return True only for genuine Plotly Figure-like objects.

    A real Figure exposes ``to_image`` *and* a ``data`` trace collection.  We
    duck-type defensively so that ``None``, strings, or arbitrary objects never
    reach the Kaleido renderer (which would raise a confusing AttributeError).
    """
    if obj is None:
        return False
    to_image = getattr(obj, "to_image", None)
    return callable(to_image) and hasattr(obj, "data")


def extract_plot_image(fig: Any, usable_width: float, tracked_streams: List[io.BytesIO]) -> Any:
    """Defensive Plotly image extraction with a styled canvas fallback.

    Robustness contract (Vectors A2 / STEP-1 headless handling):
        * Non-Figure payloads (``None``, strings, missing keys) never reach the
          Kaleido renderer -- they route straight to the fallback canvas.
        * A missing ``kaleido`` package, or a headless host lacking libX11 /
          Chromium system dependencies, is caught here and logged once as a
          clear environment notification rather than crashing the compiler.
    """
    # ---- Type firewall: anything that is not a real Figure -> fallback ----
    if not _is_plotly_figure(fig):
        logger.info("Routing figure to canvas fallback (non-Figure payload).")
        return _build_fallback_canvas(usable_width, reason="non_figure")

    # ---- Attempt genuine image extraction on an isolated deep copy ----
    local_fig = copy.deepcopy(fig)
    try:
        img_bytes = local_fig.to_image(format="png", width=800, height=600)
        stream = io.BytesIO(img_bytes)
        tracked_streams.append(stream)
        img = Image(stream, width=usable_width, height=usable_width * 0.75)
        return img
    except Exception as e:
        msg = str(e).lower()
        # Surface a clear, actionable notification for the two dominant
        # headless failure modes so operators can fix their environment.
        if "kaleido" in msg or "chromium" in msg or "libx11" in msg or "xvfb" in msg:
            logger.info(
                "Kaleido unavailable; attempting matplotlib rasterizer fallback "
                "to embed the chart image without a headless browser dependency."
            )
        else:
            logger.warning(f"Plotly image extraction failed: {e}; trying matplotlib fallback.")

        # ---- Matplotlib fallback: rebuild the chart from trace data so the
        # manuscript still embeds a real figure when Kaleido is missing. ----
        mpl_buf = _rasterize_with_matplotlib(local_fig, tracked_streams)
        if mpl_buf is not None:
            try:
                return Image(mpl_buf, width=usable_width,
                             height=usable_width * 0.75)
            except Exception as ie:
                logger.warning(f"matplotlib PNG embed failed: {ie}")

        # Final resort: styled text canvas placeholder (Vector A2 contract).
        return _build_fallback_canvas(usable_width, reason="render_error")
    finally:
        # Break the deep-copy reference so no transient figure graph lingers.
        local_fig = None


def _build_fallback_canvas(usable_width: float, reason: str = "render_error") -> Any:
    """Render the styled placeholder canvas used when a figure cannot be drawn.

    The canvas is a margined PDF bounding box stamped with the figure's
    canonical chart title, satisfying the Vector A2 defensive fallback contract.
    """
    try:
        fallback_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ])
        body = (
            "<b>[Chart: Dynamic Phase-Folded Transit Profile Data]</b><br/>"
            "<i>(Figure unavailable -- image extraction failed or headless "
            "environment without Kaleido / libX11.)</i>"
        )
        p = Paragraph(body, getSampleStyleSheet()["Normal"])
        t = Table([[p]], colWidths=[usable_width], rowHeights=[usable_width * 0.5])
        t.setStyle(fallback_style)
        return t
    except NameError:
        # reportlab not imported at all -- nothing we can render.
        return None


def _rasterize_with_matplotlib(fig: Any, tracked_streams: List[io.BytesIO]) -> Any:
    """Rebuild a Plotly Figure as a matplotlib PNG when Kaleido is unavailable.

    Plotly's native ``Figure.to_image()`` path requires the ``kaleido`` package
    (plus Chromium / libX11 on Linux), which is frequently absent on headless
    hosts and CI runners.  Rather than surrendering to the styled text
    placeholder, we re-project the figure's trace data onto matplotlib's Agg
    backend -- which has no external browser dependency and is already pinned
    in ``requirements.txt`` -- so the manuscript still embeds a real chart.

    The mapping is intentionally conservative: it supports the scatter /
    line trace shapes produced by the dashboard's phase-folded builder and
    preserves the figure's title, axis labels, and dark theme.  Any
    unrecoverable failure returns ``None`` so the caller can fall through to
    the styled canvas placeholder (preserving the Vector A2 contract).
    """
    try:
        import matplotlib
        # Force a non-interactive backend -- never let matplotlib try to open
        # a GUI window during a PDF compile.
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_rgba
    except ImportError:
        logger.warning(
            "matplotlib unavailable; cannot fall back from Kaleido. "
            "Install matplotlib to enable embedded chart images."
        )
        return None

    def _mpl_color(raw: Any, default: str) -> Any:
        """Normalize a Plotly/CSS color value into a matplotlib RGBA tuple.

        matplotlib's color parser does not understand CSS ``rgba(r,g,b,a)``
        strings, so we hand-convert those; everything else (hex, named
        colors) is delegated to ``matplotlib.colors.to_rgba``.
        """
        if not isinstance(raw, str):
            return to_rgba(default)
        s = raw.strip()
        if s.lower().startswith("rgba") or s.lower().startswith("rgb"):
            open_p = s.find("(")
            close_p = s.rfind(")")
            if open_p == -1 or close_p == -1:
                return to_rgba(default)
            inner = s[open_p + 1: close_p]
            parts = [p.strip() for p in inner.split(",")]
            try:
                if s.lower().startswith("rgba") and len(parts) == 4:
                    r, g, b, a = parts
                    return (float(r) / 255.0, float(g) / 255.0,
                            float(b) / 255.0, float(a))
                if s.lower().startswith("rgb") and len(parts) == 3:
                    r, g, b = parts
                    return (float(r) / 255.0, float(g) / 255.0,
                            float(b) / 255.0, 1.0)
            except (ValueError, IndexError):
                return to_rgba(default)
        try:
            return to_rgba(s)
        except ValueError:
            return to_rgba(default)

    try:
        layout = getattr(fig, "layout", None)
        # ---- Canvas + theme ----
        paper_bg = "#0F172A"
        plot_bg = "#0F172A"
        text_color = "#E2E8F0"
        if layout is not None:
            paper_bg_p = getattr(layout, "paper_bgcolor", None)
            plot_bg_p = getattr(layout, "plot_bgcolor", None)
            font_p = getattr(layout, "font", None)
            if isinstance(paper_bg_p, str) and paper_bg_p.startswith("rgba") and \
                    paper_bg_p.strip().endswith(",0)"):
                # Transparent paper -> use the plot bg as the page color.
                pass
            elif isinstance(paper_bg_p, str) and not paper_bg_p.startswith("rgba"):
                paper_bg = paper_bg_p
            if isinstance(plot_bg_p, str) and not plot_bg_p.startswith("rgba"):
                plot_bg = plot_bg_p
            if font_p is not None:
                fc = getattr(font_p, "color", None)
                if isinstance(fc, str):
                    text_color = fc

        dpi = 150
        width_in = 800 / dpi
        height_in = 600 / dpi
        mpl_fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
        mpl_fig.patch.set_facecolor(_mpl_color(paper_bg, paper_bg))
        ax.set_facecolor(_mpl_color(plot_bg, plot_bg))

        # ---- Traces ----
        traces = getattr(fig, "data", ()) or ()
        plotted = False
        for trace in traces:
            x = getattr(trace, "x", None)
            y = getattr(trace, "y", None)
            if x is None or y is None:
                continue
            mode = getattr(trace, "mode", "") or ""
            marker = getattr(trace, "marker", None)
            line = getattr(trace, "line", None)

            m_color = "#22D3EE"
            m_size = 4
            l_color = "#38BDF8"
            l_width = 1.5
            if marker is not None:
                mc = getattr(marker, "color", None)
                if isinstance(mc, str):
                    m_color = mc
                ms = getattr(marker, "size", None)
                if isinstance(ms, (int, float)):
                    m_size = ms
            if line is not None:
                lc = getattr(line, "color", None)
                if isinstance(lc, str):
                    l_color = lc
                lw = getattr(line, "width", None)
                if isinstance(lw, (int, float)):
                    l_width = lw

            has_markers = "markers" in mode or mode == ""
            has_lines = "lines" in mode

            m_rgba = _mpl_color(m_color, m_color)
            l_rgba = _mpl_color(l_color, l_color)
            if has_lines and has_markers:
                ax.plot(x, y, linestyle="-", color=l_rgba,
                        linewidth=l_width, marker="o", markerfacecolor=m_rgba,
                        markeredgecolor=m_rgba, markersize=m_size)
            elif has_lines:
                ax.plot(x, y, linestyle="-", color=l_rgba, linewidth=l_width)
            else:
                # Default to markers (covers our scatter case).
                ax.scatter(x, y, c=[m_rgba], s=m_size ** 2,
                           edgecolors="none")
            plotted = True

        if not plotted:
            plt.close(mpl_fig)
            return None

        # ---- Title + axes (ported from the Plotly layout) ----
        text_rgba = _mpl_color(text_color, text_color)
        title_text = None
        if layout is not None:
            title = getattr(layout, "title", None)
            if title is not None:
                title_text = getattr(title, "text", None)
        if title_text:
            ax.set_title(title_text, color=text_rgba, fontsize=12, pad=10)

        xaxis_label = None
        yaxis_label = None
        if layout is not None:
            xa = getattr(layout, "xaxis", None)
            ya = getattr(layout, "yaxis", None)
            if xa is not None:
                xt = getattr(xa, "title", None)
                if xt is not None:
                    xaxis_label = getattr(xt, "text", None)
            if ya is not None:
                yt = getattr(ya, "title", None)
                if yt is not None:
                    yaxis_label = getattr(yt, "text", None)
        if xaxis_label:
            ax.set_xlabel(xaxis_label, color=text_rgba, fontsize=10)
        if yaxis_label:
            ax.set_ylabel(yaxis_label, color=text_rgba, fontsize=10)

        # Axis chrome tuned to the dark theme.
        ax.tick_params(colors=text_rgba, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#1E293B")
        ax.grid(True, color=_mpl_color("rgba(148,163,184,0.18)", "#94A3B8"),
                linewidth=0.5)

        buf = io.BytesIO()
        mpl_fig.savefig(buf, format="png", facecolor=mpl_fig.get_facecolor(),
                        bbox_inches="tight", pad_inches=0.15)
        plt.close(mpl_fig)
        buf.seek(0)
        tracked_streams.append(buf)
        return buf
    except Exception as e:
        logger.warning(f"matplotlib figure fallback failed: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def generate_academic_report(metrics_payload: Dict[str, Any], figures: Dict[str, Any] = None) -> io.BytesIO:
    """
    Generate an automated, heavily stylized arXiv-style Academic Paper PDF in-memory.
    
    Args:
        metrics_payload: A dictionary with 'star_id' and a 'candidates' list of dicts.
        figures: A dictionary mapping figure names to Plotly Figure objects.
        
    Returns:
        io.BytesIO: The raw binary buffer stream of the generated PDF document.
    """
    if figures is None:
        figures = {}
        
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        raise ImportError("reportlab library is required. Install it via 'pip install reportlab'.")
        
    _validate_schema(metrics_payload)
    
    # Countermeasure against Pass-By-Reference Mutation
    metrics_payload = copy.deepcopy(metrics_payload)
    
    out_buffer = io.BytesIO()
    
    # 72 points per inch
    page_width, page_height = letter
    left_margin = 0.75 * inch
    right_margin = 0.75 * inch
    usable_width = page_width - (left_margin + right_margin)
    
    doc = SimpleDocTemplate(
        out_buffer,
        pagesize=letter,
        rightMargin=right_margin,
        leftMargin=left_margin,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )
    
    styles = getSampleStyleSheet()
    
    # Premium Design Language Styling Rules
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=colors.HexColor("#1E293B"), # Deep Charcoal
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=20
    )
    
    heading2_style = ParagraphStyle(
        'ReportHeading2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.HexColor("#1E293B"), # Deep Charcoal
        spaceAfter=6
    )
    
    normal_style = ParagraphStyle(
        'ReportNormal',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        textColor=colors.black,
        spaceAfter=10,
        leading=14
    )
    
    story = []
    tracked_streams = []
    
    try:
        # Document Header
        star_id = sanitize_text(str(metrics_payload.get('star_id', 'Unknown')))
        story.append(Paragraph(f"Astraeus Discovery Report: Target {star_id}", title_style))
        timestamp = datetime.datetime.now().strftime("%B %d, %Y")
        story.append(Paragraph(f"Automated Pipeline Export | Generated {timestamp}", subtitle_style))
        
        # Executive Abstract Box
        num_candidates = len(metrics_payload['candidates'])
        abstract_text = (f"This report presents an automated structural analysis and candidate validation "
                         f"for <b>{star_id}</b>. The pipeline has isolated <b>{num_candidates}</b> planetary "
                         f"candidates matching the confidence criteria.")
        
        abstract_p = Paragraph(sanitize_text(abstract_text), normal_style)
        abstract_table = Table([[abstract_p]], colWidths=[usable_width])
        abstract_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")), # Soft muted gray
            ('LINEBEFORE', (0,0), (0,-1), 3, colors.HexColor("#B91C1C")), # Deep Crimson accent
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('LEFTPADDING', (0,0), (-1,-1), 15),
            ('RIGHTPADDING', (0,0), (-1,-1), 15),
        ]))
        story.append(abstract_table)
        story.append(Spacer(1, 20))
        
        # Section Header Rule Line Helper
        rule_table = Table([['']], colWidths=[usable_width], rowHeights=[1])
        rule_table.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1"))
        ]))
        
        # Section 1: Introduction & Data Diagnostics
        story.append(Paragraph("1. Introduction & Data Diagnostics", heading2_style))
        story.append(Spacer(1, 2))
        story.append(rule_table)
        story.append(Spacer(1, 10))
        
        intro_text = metrics_payload.get('introduction', 'Standard observational baseline diagnostics were performed. The flux data was detrended and cleaned of systematic anomalies.')
        story.append(Paragraph(sanitize_text(intro_text), normal_style))
        
        # Section 2: Transit Optimization Analysis
        story.append(Spacer(1, 15))
        story.append(Paragraph("2. Transit Optimization Analysis", heading2_style))
        story.append(Spacer(1, 2))
        story.append(rule_table)
        story.append(Spacer(1, 10))
        
        opt_text = metrics_payload.get('optimization_summary', 'Multi-planet grid optimization resolved planetary periods with a sub-pixel precision algorithm using a dynamic baseline scale. Dual-Zone Grid variables were successfully applied.')
        story.append(Paragraph(sanitize_text(opt_text), normal_style))
        
        # Section 3: Physical Properties Table
        story.append(Spacer(1, 15))
        story.append(Paragraph("3. Planetary Properties Ledger", heading2_style))
        story.append(Spacer(1, 2))
        story.append(rule_table)
        story.append(Spacer(1, 10))
        
        header_row = ["Candidate ID", "Period (days)", "SNR", "Depth", "Epoch"]
        candidate_rows = []
        for cand in metrics_payload['candidates']:
            candidate_rows.append([
                sanitize_text(str(cand.get('candidate_id', cand.get('planet_id', '-')))),
                sanitize_text(f"{cand.get('period', 0.0):.4f}"),
                sanitize_text(f"{cand.get('snr', 0.0):.2f}"),
                sanitize_text(f"{cand.get('depth', 0.0):.6f}"),
                sanitize_text(f"{cand.get('epoch', 0.0):.4f}")
            ])
            
        def build_table(data_rows, is_first=False):
            table_data = [header_row] + data_rows
            wrapped_data = []
            for row in table_data:
                wrapped_data.append([Paragraph(f"<b>{cell}</b>" if i == 0 else cell, normal_style) for i, cell in enumerate(row)])
                
            col_w = usable_width / 5.0
            t = Table(wrapped_data, colWidths=[col_w]*5)
            
            t_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ]
            for i in range(1, len(table_data)):
                if i % 2 == 0:
                    t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F8FAFC")))
                else:
                    t_style.append(('BACKGROUND', (0, i), (-1, i), colors.white))
            t.setStyle(TableStyle(t_style))
            return t

        MAX_ROWS = 8
        if not candidate_rows:
            # Handle empty case
            story.append(build_table([]))
        else:
            for i in range(0, len(candidate_rows), MAX_ROWS):
                chunk = candidate_rows[i:i + MAX_ROWS]
                props_table = build_table(chunk, is_first=(i==0))
                story.append(props_table)
                if i + MAX_ROWS < len(candidate_rows):
                    story.append(Spacer(1, 15))
        
        # Figures
        if figures:
            story.append(Spacer(1, 20))
            story.append(Paragraph("4. Figure Layouts", heading2_style))
            story.append(Spacer(1, 2))
            story.append(rule_table)
            story.append(Spacer(1, 10))
            
            for fig_name, fig_obj in figures.items():
                fig_title = fig_name.replace('_', ' ').title()
                story.append(Paragraph(sanitize_text(f"<b>Figure:</b> {fig_title}"), normal_style))
                story.append(Spacer(1, 5))
                img_flowable = extract_plot_image(fig_obj, usable_width, tracked_streams)
                if img_flowable:
                    story.append(img_flowable)
                story.append(Spacer(1, 15))
                
        # Build the PDF directly to the byte stream
        doc.build(story, canvasmaker=NumberedCanvas)
        
    finally:
        # Cleanup memory streams and force garbage collection
        for stream in tracked_streams:
            stream.close()
        gc.collect()

    # Reset pointer for reading
    out_buffer.seek(0)
    return out_buffer


def generate_completeness_report(result, config, fig_paths):
    """Produce a JSON-shaped summary of one completeness sweep.

    Distinct from :func:`generate_academic_report`: completeness data does not
    fit the {star_id, candidates: [...]} schema enforced by
    :func:`_validate_schema`. This function returns a plain dict, suitable for
    a future UI panel or a future PDF-rendering bucket.

    Args:
        result: A :class:`astraeus.simulation.completeness.CompletenessSweepResult`.
            The duck-typed access (no import) avoids a circular import.
        config: A :class:`astraeus.simulation.completeness.CompletenessSweepConfig`,
            used for human-readable summary fields.
        fig_paths: dict mapping figure names to Path objects.

    Returns:
        dict with keys: schema_version, generated_at_iso, mode, config_summary,
        summary_stats, per_cell_table, figure_paths.
    """
    import numpy as _np

    valid = _np.isfinite(result.recovery_rate)
    overall_recovery = (
        float(_np.mean(result.recovery_rate[valid])) if valid.any() else 0.0
    )

    flat = result.recovery_rate.flatten()
    valid_flat = flat[_np.isfinite(flat)]
    if valid_flat.size:
        worst_idx = int(_np.argmin(flat))
        best_idx = int(_np.argmax(flat))
        stride_p = result.radius_ratios.size * result.snrs.size
        stride_d = result.snrs.size
        worst = {
            "period_days": float(result.periods_days[worst_idx // stride_p]),
            "radius_ratio": float(
                result.radius_ratios[(worst_idx // stride_d) % result.radius_ratios.size]
            ),
            "snr": float(result.snrs[worst_idx % result.snrs.size]),
            "recovery_rate": float(flat[worst_idx]),
        }
        best = {
            "period_days": float(result.periods_days[best_idx // stride_p]),
            "radius_ratio": float(
                result.radius_ratios[(best_idx // stride_d) % result.radius_ratios.size]
            ),
            "snr": float(result.snrs[best_idx % result.snrs.size]),
            "recovery_rate": float(flat[best_idx]),
        }
    else:
        worst = best = {}

    period_err_flat = result.period_err_median.flatten()
    period_err_valid = period_err_flat[_np.isfinite(period_err_flat)]
    mean_period_err = (
        float(_np.mean(period_err_valid)) if period_err_valid.size else None
    )

    per_cell: list[dict] = []
    for i, p in enumerate(result.periods_days):
        for j, d in enumerate(result.radius_ratios):
            for k, s in enumerate(result.snrs):
                per_cell.append({
                    "period_days": float(p),
                    "radius_ratio": float(d),
                    "snr": float(s),
                    "recovery_rate": float(result.recovery_rate[i, j, k])
                    if _np.isfinite(result.recovery_rate[i, j, k])
                    else None,
                    "n_recovered": int(result.n_recovered[i, j, k]),
                    "period_err_median": float(result.period_err_median[i, j, k])
                    if _np.isfinite(result.period_err_median[i, j, k])
                    else None,
                    "depth_err_median": float(result.depth_err_median[i, j, k])
                    if _np.isfinite(result.depth_err_median[i, j, k])
                    else None,
                })

    return {
        "schema_version": 1,
        "generated_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": "full_pipeline" if config.use_full_pipeline else "bls_only",
        "config_summary": {
            "period_min_days": config.period_min_days,
            "period_max_days": config.period_max_days,
            "period_count": config.period_count,
            "radius_ratio_min": config.radius_ratio_min,
            "radius_ratio_max": config.radius_ratio_max,
            "radius_ratio_count": config.radius_ratio_count,
            "snr_values": list(config.snr_values),
            "n_injections": config.n_injections,
            "duration_days": config.duration_days,
            "samples": config.samples,
        },
        "summary_stats": {
            "total_cells": int(result.shape[0] * result.shape[1] * result.shape[2]),
            "overall_recovery_rate": overall_recovery,
            "mean_period_err_median_across_recovered_cells": mean_period_err,
            "worst_performing_cell": worst,
            "best_performing_cell": best,
            "total_runtime_seconds": result.total_runtime_seconds,
            "cache_hits": result.cache_hits,
            "cache_misses": result.cache_misses,
        },
        "per_cell_table": per_cell,
        "figure_paths": {k: str(v) for k, v in (fig_paths or {}).items()},
    }
