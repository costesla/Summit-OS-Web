
from fpdf import FPDF
import datetime

class SummitSyncPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(20, 40, 100)
        self.cell(0, 10, 'SUMMIT SYNC | OPERATIONAL WALKTHROUGH', 0, 1, 'C')
        self.set_draw_color(20, 40, 100)
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()} | Generated on {datetime.datetime.now().strftime("%Y-%m-%d")}', 0, 0, 'C')

def create_pdf():
    pdf = SummitSyncPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Title Section
    pdf.set_font('Arial', 'B', 16)
    pdf.set_text_color(0)
    pdf.cell(0, 10, 'OCR Sync and Cross-Validation Verified', 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_font('Arial', '', 11)
    content = "The Summit Sync pipeline is now operational with a robust cross-validation system. We have established a continuous flow that audits Uber trip data against Tesla telemetry."
    pdf.multi_cell(0, 7, content)
    pdf.ln(5)

    # Key Accomplishments
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(20, 40, 100)
    pdf.cell(0, 10, 'Key Accomplishments', 0, 1, 'L')
    pdf.ln(2)
    
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(0)
    points = [
        ("Cross-Validation Schema", "Upgraded the database to store dedicated Uber and Tessie metrics for side-by-side auditing."),
        ("Telemetry Source of Truth", "System now prefers high-precision Tesla telemetry for primary distance and duration metrics."),
        ("Enhanced OCR Parsing", "Improved logic to capture standalone upfront offers from Uber 'Accept' screens."),
        ("Verified Authentication", "Resolved Azure Vision API issues using robust Azure AD authentication fallbacks."),
        ("Jan 16 Audit Sync", "Successfully processed 72+ trips for Jan 16th to verify end-to-end data integrity.")
    ]
    
    for title, desc in points:
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(10, 7, chr(127), 0, 0) # Bullet
        pdf.cell(0, 7, f"{title}:", 0, 1)
        pdf.set_x(20)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 7, desc)
        pdf.ln(2)

    # Monitoring Section
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(20, 40, 100)
    pdf.cell(0, 10, 'Operational Monitoring', 0, 1, 'L')
    pdf.ln(2)
    
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(0)
    monitor_text = [
        "Local Audit: Run 'python summit_sync/scripts/view_data.py' to see live variance tables.",
        "AI Data Lake: Reports are automatically synced to OneDrive /SummitOS/Daily_Reports/.",
        "Historical Refresh: Run 'python summit_sync/scripts/export_daily_sales.py --all' to backfill all data.",
        "Cloud Health: Monitor the 'summitsyncfuncus23436' Azure Function for real-time logs."
    ]
    
    for item in monitor_text:
        pdf.cell(10, 7, ">", 0, 0)
        pdf.multi_cell(0, 7, item)
        pdf.ln(1)

    # AI Readiness
    pdf.ln(5)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 10, '   AI and Copilot Readiness', 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 11)
    ai_text = "The system is fully optimized for Microsoft Copilot recall. Data is exported with semantic headers and raw OCR 'Notes', allowing AI to explain trip details and verify variances directly from your OneDrive."
    pdf.multi_cell(0, 7, ai_text, border=1)

    pdf_path = r"C:\Users\PeterTeehan\OneDrive - COS Tesla LLC\SummitOS\Summit_Sync_Walkthrough.pdf"
    pdf.output(pdf_path)
    print(f"PDF Successfully generated at: {pdf_path}")

if __name__ == "__main__":
    create_pdf()
