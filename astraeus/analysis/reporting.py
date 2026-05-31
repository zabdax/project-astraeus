import os
import datetime
from typing import Dict, Any, List
import logging

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None
    
logger = logging.getLogger(__name__)

def generate_report(data_summary: Dict[str, Any], figures_paths: List[str], discussion_text: Dict[str, str], output_format: str = "markdown") -> str:
    """
    Implement an export engine that compiles data into Markdown or PDF.
    
    Args:
        data_summary: Dictionary of MCMC results or data summary.
        figures_paths: List of file paths to the generated figures.
        discussion_text: Dictionary output from explanation.py.
        output_format: 'markdown' or 'pdf'
        
    Returns:
        Path to the generated report.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"ASTRAEUS_Report_{timestamp}"
    
    # Ensure outputs directory exists
    os.makedirs("outputs", exist_ok=True)
    
    if output_format.lower() == "markdown":
        output_path = os.path.join("outputs", f"{filename}.md")
        _generate_markdown(data_summary, figures_paths, discussion_text, output_path)
    elif output_format.lower() == "pdf":
        output_path = os.path.join("outputs", f"{filename}.pdf")
        _generate_pdf(data_summary, figures_paths, discussion_text, output_path)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
        
    logger.info(f"Report generated successfully at {output_path}")
    return output_path

def _generate_markdown(data_summary: Dict[str, Any], figures_paths: List[str], discussion_text: Dict[str, str], output_path: str):
    lines = []
    lines.append("# ASTRAEUS MCMC Retrieval Report")
    lines.append("")
    
    # MCMC Results Table
    lines.append("## MCMC Results Summary")
    lines.append("| Parameter | Value |")
    lines.append("|---|---|")
    for k, v in data_summary.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    
    # Discussion Text
    lines.append("## Scientific Explanation")
    if "physics_interpretation" in discussion_text:
        lines.append("### Physics Interpretation")
        lines.append(discussion_text["physics_interpretation"])
        lines.append("")
        
    if "parameter_breakdown" in discussion_text:
        lines.append("### Parameter Breakdown")
        lines.append(discussion_text["parameter_breakdown"])
        lines.append("")
        
    if "uncertainty_analysis" in discussion_text:
        lines.append("### Uncertainty Analysis")
        lines.append(discussion_text["uncertainty_analysis"])
        lines.append("")
        
    # Figures
    if figures_paths:
        lines.append("## Figures")
        for path in figures_paths:
            caption = os.path.basename(path)
            # Use forward slashes for markdown image paths if needed, 
            # though standard markdown usually handles relative paths fine.
            # Using posix path format for markdown compatibility.
            posix_path = path.replace("\\", "/")
            lines.append(f"![{caption}]({posix_path})")
            lines.append("")
            
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _generate_pdf(data_summary: Dict[str, Any], figures_paths: List[str], discussion_text: Dict[str, str], output_path: str):
    if FPDF is None:
        raise ImportError("fpdf library is required to generate PDF reports. Install it via 'pip install fpdf2'.")
        
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "ASTRAEUS MCMC Retrieval Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    
    # MCMC Results
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "MCMC Results Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    
    # Table Header
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 8, "Parameter", border=1)
    pdf.cell(90, 8, "Value", border=1, new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 10)
    for k, v in data_summary.items():
        pdf.cell(90, 8, str(k), border=1)
        pdf.cell(90, 8, str(v), border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(10)
    
    # Discussion Text
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Scientific Explanation", new_x="LMARGIN", new_y="NEXT")
    
    sections = [
        ("Physics Interpretation", "physics_interpretation"),
        ("Parameter Breakdown", "parameter_breakdown"),
        ("Uncertainty Analysis", "uncertainty_analysis")
    ]
    
    for title, key in sections:
        if key in discussion_text:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, discussion_text[key])
            pdf.ln(5)
            
    # Figures
    if figures_paths:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 10, "Figures", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        for path in figures_paths:
            if os.path.exists(path):
                # We will insert the image and scale it to fit the page width (leave margins)
                # FPDF uses dimensions in mm (default page width = 210mm)
                pdf.image(path, w=170)
                pdf.ln(5)
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(0, 5, os.path.basename(path), align="C", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(10)
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 10, f"Image not found: {path}", new_x="LMARGIN", new_y="NEXT")
                
    pdf.output(output_path)
