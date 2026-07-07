"""
Resume PDF generation module using ReportLab.

Generates a modern, professional, single-column resume PDF from structured profile data.
"""

from __future__ import annotations

import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Theme Colors
PRIMARY_COLOR = colors.HexColor("#2563eb")  # Accent blue
TEXT_COLOR = colors.HexColor("#1f2937")     # Dark charcoal/slate
MUTED_TEXT = colors.HexColor("#4b5563")     # Gray
BORDER_COLOR = colors.HexColor("#e5e7eb")   # Light gray for dividers


class NumberedCanvas(canvas.Canvas):
    """Canvas that computes total pages dynamically and adds page numbers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(MUTED_TEXT)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 36, page_text)
        self.restoreState()


def generate_resume_pdf(profile_data: dict) -> bytes:
    """Generate a PDF of the resume in memory and return the raw bytes.

    profile_data structure:
      {
        "name": str,
        "email": str,
        "phone": str,
        "location": str,
        "country": str,
        "summary": str,
        "skills": list[str],
        "experience": list[dict],
        "education": list[dict],
        "projects": list[dict],
        "certifications": list[dict]
      }
    """
    buffer = BytesIO()
    
    # Page settings: 0.75 inch margins
    margin = 54  # 0.75 * 72
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    
    styles = getSampleStyleSheet()
    
    # Custom modern paragraph styles
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=PRIMARY_COLOR,
        alignment=1  # Centered
    )
    
    contact_style = ParagraphStyle(
        'ContactStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=MUTED_TEXT,
        alignment=1  # Centered
    )
    
    sec_title_style = ParagraphStyle(
        'SecTitleStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=PRIMARY_COLOR,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=TEXT_COLOR
    )
    
    bold_body_style = ParagraphStyle(
        'BoldBodyStyle',
        parent=body_style,
        fontName='Helvetica-Bold'
    )
    
    item_header_style = ParagraphStyle(
        'ItemHeaderStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=TEXT_COLOR,
        keepWithNext=True
    )
    
    item_subheader_style = ParagraphStyle(
        'ItemSubheaderStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=13,
        textColor=MUTED_TEXT,
        keepWithNext=True
    )
    
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=TEXT_COLOR,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3
    )

    story = []
    
    # ── Header ──
    story.append(Paragraph(profile_data.get("name", "Your Name") or "Your Name", name_style))
    story.append(Spacer(1, 4))
    
    # Contact Details
    contact_parts = []
    if profile_data.get("email"):
        contact_parts.append(profile_data["email"])
    if profile_data.get("phone"):
        contact_parts.append(profile_data["phone"])
    loc_parts = []
    if profile_data.get("location"):
        loc_parts.append(profile_data["location"])
    if profile_data.get("country"):
        loc_parts.append(profile_data["country"])
    if loc_parts:
        contact_parts.append(", ".join(loc_parts))
        
    contact_str = "  |  ".join(contact_parts)
    story.append(Paragraph(contact_str, contact_style))
    story.append(Spacer(1, 15))
    
    # Helper to add section headers with clean line
    def add_section_header(title):
        story.append(Spacer(1, 10))
        story.append(Paragraph(title.upper(), sec_title_style))
        story.append(HRFlowable(
            width="100%", thickness=1, color=PRIMARY_COLOR, spaceBefore=2, spaceAfter=8
        ))
        
    # ── Summary ──
    if profile_data.get("summary"):
        add_section_header("Professional Summary")
        story.append(Paragraph(profile_data["summary"], body_style))
        
    # ── Skills ──
    if profile_data.get("skills"):
        add_section_header("Skills & Technologies")
        skills_str = ", ".join(profile_data["skills"])
        story.append(Paragraph(skills_str, body_style))
        
    # ── Experience ──
    if profile_data.get("experience"):
        add_section_header("Professional Experience")
        for exp in profile_data["experience"]:
            exp_story = []
            
            # Header line: Job Title + Dates
            company = exp.get("company", "Company")
            title = exp.get("title", "Role")
            start = exp.get("start_date", "")
            end = "Present" if exp.get("is_current") else exp.get("end_date", "")
            date_str = f"{start} - {end}" if start or end else ""
            
            # Right-aligned date structure via a clean table
            title_p = Paragraph(f"{title} &mdash; <b>{company}</b>", item_header_style)
            date_p = Paragraph(f"<font color='{MUTED_TEXT.hexval()}'>{date_str}</font>", ParagraphStyle('RightText', parent=body_style, alignment=2))
            
            t = Table([[title_p, date_p]], colWidths=[letter[0] - 2 * margin - 150, 150])
            t.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
            ]))
            exp_story.append(t)
            
            # Bullet points
            bullets = exp.get("bullets", [])
            for bullet in bullets:
                if bullet.strip():
                    exp_story.append(Paragraph(f"&bull;&nbsp;&nbsp;{bullet}", bullet_style))
                    
            story.append(KeepTogether(exp_story))
            story.append(Spacer(1, 8))
            
    # ── Projects ──
    if profile_data.get("projects"):
        add_section_header("Projects")
        for proj in profile_data["projects"]:
            proj_story = []
            name = proj.get("name", "Project Name")
            tech = proj.get("technologies", [])
            desc = proj.get("description", "")
            
            tech_str = f" ({', '.join(tech)})" if tech else ""
            proj_story.append(Paragraph(f"<b>{name}</b>{tech_str}", item_header_style))
            if desc:
                proj_story.append(Paragraph(desc, body_style))
                
            story.append(KeepTogether(proj_story))
            story.append(Spacer(1, 6))

    # ── Education ──
    if profile_data.get("education"):
        add_section_header("Education")
        for edu in profile_data["education"]:
            edu_story = []
            inst = edu.get("institution", "")
            deg = edu.get("degree", "")
            field = edu.get("field", "")
            year = edu.get("year", "")
            
            deg_field = f"{deg} in {field}" if deg and field else (deg or field)
            
            inst_p = Paragraph(f"<b>{inst}</b>", item_header_style)
            year_p = Paragraph(f"<font color='{MUTED_TEXT.hexval()}'>{year}</font>", ParagraphStyle('RightTextEdu', parent=body_style, alignment=2))
            
            t = Table([[inst_p, year_p]], colWidths=[letter[0] - 2 * margin - 100, 100])
            t.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
            ]))
            edu_story.append(t)
            if deg_field:
                edu_story.append(Paragraph(deg_field, item_subheader_style))
                
            story.append(KeepTogether(edu_story))
            story.append(Spacer(1, 6))
            
    # ── Certifications ──
    if profile_data.get("certifications"):
        add_section_header("Certifications")
        cert_story = []
        for cert in profile_data["certifications"]:
            name = cert.get("name")
            if name:
                cert_story.append(Paragraph(f"&bull;&nbsp;&nbsp;{name}", bullet_style))
        story.append(KeepTogether(cert_story))
        
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
