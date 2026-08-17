"""테스트용 샘플 정책 문서 PDF를 생성하는 일회성 스크립트.
실제 앱 로직과는 무관하며, parser.py 동작 확인용이다.
"""

from fpdf import FPDF

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 10, "Employee Onboarding Policy", new_x="LMARGIN", new_y="NEXT")

sections = [
    ("1. Working Hours", "Standard working hours are 9 AM to 6 PM, Monday through Friday. Employees may request flexible schedules with manager approval."),
    ("2. Remote Work", "Employees may work remotely up to two days per week. Remote work requests must be submitted through the HR portal at least one week in advance."),
    ("3. Leave Policy", "Full-time employees receive 15 days of paid annual leave. Unused leave may be carried over up to 5 days into the next calendar year."),
    ("4. Code of Conduct", "All employees are expected to treat colleagues with respect, maintain confidentiality of company information, and avoid conflicts of interest."),
]

pdf.set_font("Helvetica", "", 12)
for title, body in sections:
    pdf.ln(8)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 8, title)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 8, body)

pdf.output("sample_docs/sample_policy.pdf")
print("생성 완료: sample_docs/sample_policy.pdf")
