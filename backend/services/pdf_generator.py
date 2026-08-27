"""
COS Tesla LLC - Executive PDF Report Generator
Phase 2 Implementation Module (Corrected & Hardened)
Author: Google Antigravity
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

class ExecutivePDFGenerator:
    def __init__(self):
        self.primary_color = colors.HexColor("#0F172A")    # Slate 900
        self.accent_color = colors.HexColor("#0EA5E9")     # Electric Sky Blue
        self.success_color = colors.HexColor("#15803D")    # Dark Green
        self.danger_color = colors.HexColor("#DC2626")     # Red
        self.bg_light = colors.HexColor("#F8FAFC")         # Slate 50
        self.border_color = colors.HexColor("#E2E8F0")     # Slate 200
        self.text_dark = colors.HexColor("#1E293B")        # Slate 800
        self.text_muted = colors.HexColor("#64748B")       # Slate 500

    def generate_daily_pdf(self, data: Dict[str, Any], sha256_hash: str, output_path: str, is_synthetic: bool = True) -> str:
        """Generates a formal branded single-page daily executive PDF with calendar-accurate weekday calculation."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'DocTitle',
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.white
        )
        date_badge_style = ParagraphStyle(
            'DateBadge',
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=self.accent_color,
            alignment=TA_RIGHT
        )
        synthetic_banner_style = ParagraphStyle(
            'SyntheticBanner',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#B45309"),
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'SectionHeading',
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=14,
            textColor=self.primary_color,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'BodyTextCustom',
            fontName='Helvetica',
            fontSize=9,
            leading=13.5,
            textColor=self.text_dark
        )
        bullet_style = ParagraphStyle(
            'BulletCustom',
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=self.text_dark,
            leftIndent=12,
            firstLineIndent=-8
        )
        footer_style = ParagraphStyle(
            'FooterStyle',
            fontName='Helvetica',
            fontSize=7.5,
            leading=10.5,
            textColor=self.text_muted,
            alignment=TA_CENTER
        )

        story = []

        # Derive calendar-accurate weekday
        try:
            dt = datetime.strptime(data["report_date"], "%Y-%m-%d")
            formatted_date_label = dt.strftime("%A, %B %d, %Y")
        except Exception:
            formatted_date_label = data["report_date"]

        # 1. Header Banner
        header_data = [
            [
                Paragraph("<b>COS TESLA LLC</b><br/><font color='#94A3B8' size=9>DAILY EXECUTIVE INTELLIGENCE BRIEFING</font>", title_style),
                Paragraph(f"<b>REPORT DATE</b><br/>{formatted_date_label}", date_badge_style)
            ]
        ]
        header_table = Table(header_data, colWidths=[350, 190])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.primary_color),
            ('PADDING', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 3, self.accent_color),
        ]))
        story.append(header_table)

        # Optional Synthetic Watermark Banner
        if is_synthetic:
            synth_table = Table([[
                Paragraph("<b>SYNTHETIC TEST DATA — NOT ACTUAL COS TESLA LLC FINANCIAL RESULTS</b>", synthetic_banner_style)
            ]], colWidths=[540])
            synth_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#F59E0B")),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(Spacer(1, 4))
            story.append(synth_table)

        story.append(Spacer(1, 10))

        # 2. Key Metrics Grid
        kpi_data = [
            [
                Paragraph("<font color='#64748B' size=7.5><b>GROSS REVENUE</b></font>", body_style),
                Paragraph("<font color='#166534' size=7.5><b>NET OPERATING PROFIT</b></font>", body_style),
                Paragraph("<font color='#64748B' size=7.5><b>TOTAL EXPENSES</b></font>", body_style),
                Paragraph("<font color='#64748B' size=7.5><b>TOTAL TRIPS</b></font>", body_style),
            ],
            [
                Paragraph(f"<font size=13 color='#0F172A'><b>${data['gross_revenue']:,.2f}</b></font>", body_style),
                Paragraph(f"<font size=13 color='#15803D'><b>${data['net_profit']:,.2f}</b></font>", body_style),
                Paragraph(f"<font size=13 color='#DC2626'><b>-${data['total_expenses']:,.2f}</b></font>", body_style),
                Paragraph(f"<font size=13 color='#0F172A'><b>{data['trip_count']} Trips</b></font>", body_style),
            ],
            [
                Paragraph("<font color='#64748B' size=7>Total daily revenue</font>", body_style),
                Paragraph(f"<font color='#166534' size=7><b>{data['net_margin_pct']}% Margin</b></font>", body_style),
                Paragraph("<font color='#64748B' size=7>Fleet operating costs</font>", body_style),
                Paragraph(f"<font color='#64748B' size=7>${data['avg_rev_per_trip']:,.2f} avg/trip</font>", body_style),
            ]
        ]
        kpi_table = Table(kpi_data, colWidths=[132, 137, 137, 134])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.bg_light),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#F0FDF4")),
            ('BACKGROUND', (2, 0), (2, -1), self.bg_light),
            ('BACKGROUND', (3, 0), (3, -1), self.bg_light),
            ('BOX', (0, 0), (0, -1), 1, self.border_color),
            ('BOX', (1, 0), (1, -1), 1, colors.HexColor("#BBF7D0")),
            ('BOX', (2, 0), (2, -1), 1, self.border_color),
            ('BOX', (3, 0), (3, -1), 1, self.border_color),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 10))

        # 3. Revenue Composition Table
        story.append(Paragraph("REVENUE MIX & COMPOSITION", heading_style))
        mix_data = [
            ["Platform / Channel", "Gross Amount", "Share %", "Status"],
            ["Uber Platform Revenue", f"${data['uber_revenue']:,.2f}", f"{data['uber_mix_pct']}%", "Reconciled"],
            ["Private Charter / Direct Clients", f"${data['private_revenue']:,.2f}", f"{data['private_mix_pct']}%", "Reconciled"],
            ["Total Gross Revenue", f"${data['gross_revenue']:,.2f}", "100.0%", "Balanced"]
        ]
        mix_table = Table(mix_data, colWidths=[240, 100, 100, 100])
        mix_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, self.border_color),
            ('BACKGROUND', (0, -1), (-1, -1), self.bg_light),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        story.append(mix_table)
        story.append(Spacer(1, 10))

        # 4. Executive Summary
        story.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
        story.append(Paragraph(data['executive_summary'], body_style))
        story.append(Spacer(1, 8))

        # 5. Operational Highlights
        story.append(Paragraph("OPERATIONAL HIGHLIGHTS", heading_style))
        for line in [l.strip().lstrip('-*•').strip() for l in data['operational_highlights'].split('\n') if l.strip()]:
            story.append(Paragraph(f"• {line}", bullet_style))
        story.append(Spacer(1, 8))

        # 6. Items Requiring Attention
        attention_lines = [l.strip().lstrip('-*•').strip() for l in data['items_attention'].split('\n') if l.strip()]
        if attention_lines and attention_lines[0] != "N/A":
            story.append(Paragraph("ITEMS REQUIRING ATTENTION", heading_style))
            for line in attention_lines:
                story.append(Paragraph(f"<font color='#B45309'><b>!</b></font> {line}", bullet_style))
            story.append(Spacer(1, 8))

        # 7. Forward Outlook
        story.append(Paragraph("FORWARD OUTLOOK & COMMENTARY", heading_style))
        for line in [l.strip().lstrip('-*•').strip() for l in data['outlook'].split('\n') if l.strip()]:
            story.append(Paragraph(line, body_style))
        story.append(Spacer(1, 12))

        # 8. Footer & Forensic Verification
        story.append(HRFlowable(width="100%", thickness=0.5, color=self.border_color, spaceBefore=0, spaceAfter=6))
        story.append(Paragraph(
            f"Prepared automatically by <b>Summit Intelligence 2.0</b> for COS Tesla LLC.<br/>"
            f"Cryptographic Audit Checksum: <font face='Courier'>{sha256_hash}</font><br/>"
            f"Confidential — Transmitted strictly for Peter Teehan (Internal Validation Stage).",
            footer_style
        ))

        doc.build(story)
        return output_path
