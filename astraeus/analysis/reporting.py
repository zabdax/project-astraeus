import io
import gc
import copy
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
    """Sanitize text for basic ReportLab core fonts."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    
    replacements = {
        r'α': 'alpha', r'β': 'beta', r'γ': 'gamma', r'δ': 'delta',
        r'θ': 'theta', r'σ': 'sigma', r'μ': 'mu', r'π': 'pi',
        r'±': '+/-', r'°': ' deg', r'≥': '>=', r'≤': '<=',
        r'×': 'x', r'≈': '~', r'≠': '!=',
        r'—': '-', r'–': '-', r'”': '"', r'“': '"', r'’': "'", r'‘': "'"
    }
    for pattern, replacement in replacements.items():
        text = text.replace(pattern, replacement)
    
    # Remove any remaining non-ascii characters
    return text.encode('ascii', 'ignore').decode('ascii')


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


def extract_plot_image(fig: Any, usable_width: float, tracked_streams: List[io.BytesIO]) -> Any:
    """Defensive Plotly image extraction with fallback."""
    local_fig = copy.deepcopy(fig)
    try:
        # Kaleido/Orca is usually required for this
        img_bytes = local_fig.to_image(format="png", width=800, height=600)
        stream = io.BytesIO(img_bytes)
        tracked_streams.append(stream)
        
        # Image aspect ratio 800:600 = 4:3 -> height = width * 0.75
        img = Image(stream, width=usable_width, height=usable_width * 0.75)
        return img
    except Exception as e:
        logger.warning(f"Failed to extract plot image: {e}")
        # Fallback Box
        try:
            fallback_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ])
            p = Paragraph("<b>Interactive Plot Placeholder</b><br/><i>(Image extraction failed or headless environment)</i>", 
                          getSampleStyleSheet()["Normal"])
            t = Table([[p]], colWidths=[usable_width], rowHeights=[usable_width * 0.5])
            t.setStyle(fallback_style)
            return t
        except NameError:
            # reportlab not imported
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
        
        table_data = [["Candidate ID", "Period (days)", "SNR", "Depth", "Epoch"]]
        for cand in metrics_payload['candidates']:
            table_data.append([
                sanitize_text(str(cand.get('candidate_id', cand.get('planet_id', '-')))),
                sanitize_text(f"{cand.get('period', 0.0):.4f}"),
                sanitize_text(f"{cand.get('snr', 0.0):.2f}"),
                sanitize_text(f"{cand.get('depth', 0.0):.6f}"),
                sanitize_text(f"{cand.get('epoch', 0.0):.4f}")
            ])
            
        # Wrapping in paragraphs for text wrapping
        wrapped_data = []
        for row in table_data:
            wrapped_data.append([Paragraph(f"<b>{cell}</b>" if i == 0 else cell, normal_style) for i, cell in enumerate(row)])
            
        col_w = usable_width / 5.0
        props_table = Table(wrapped_data, colWidths=[col_w]*5)
        
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")), # Deep Charcoal header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")), # Soft gray layout border
        ]
        
        # Alternating row colors
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F8FAFC")))
            else:
                t_style.append(('BACKGROUND', (0, i), (-1, i), colors.white))
                
        props_table.setStyle(TableStyle(t_style))
        story.append(props_table)
        
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
