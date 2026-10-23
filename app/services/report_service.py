from io import BytesIO
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.prediction import Prediction
from app.models.report import Report
from app.services.audit_service import add_audit_event

DISCLAIMER = "RiskSense AI provides risk estimates for decision support and does not replace professional medical diagnosis or treatment."


def create_report(db: Session, patient: Patient, prediction_id: UUID, actor_id: UUID) -> Report:
    prediction = db.scalar(select(Prediction).where(Prediction.id == prediction_id, Prediction.patient_id == patient.id))
    if prediction is None:
        raise LookupError("Prediction not found.")
    existing = db.scalar(select(Report).where(Report.patient_id == patient.id, Report.prediction_id == prediction.id))
    if existing is not None:
        return existing
    label = "Heart Disease" if prediction.prediction_target == "heart_disease" else "Diabetes"
    report = Report(
        patient_id=patient.id, prediction_id=prediction.id, report_type="risk_analysis",
        title=f"RiskSense AI {label} Risk Analysis Report",
        summary=(f"Estimated {label} risk classification: {prediction.risk_classification}. "
                 "This result is decision support and is not a diagnosis."),
        recommendations=None,
        report_data={
            "patient_reference": str(patient.id), "analysis_type": prediction.prediction_target,
            "analysis_at": prediction.predicted_at.isoformat(), "model_version": prediction.model_version,
            "risk_score": prediction.risk_score, "risk_classification": prediction.risk_classification,
            "decision_threshold": prediction.decision_threshold,
            "input_snapshot": prediction.input_data or {}, "disclaimer": DISCLAIMER,
        },
    )
    db.add(report)
    db.flush()
    add_audit_event(db, "REPORT_GENERATED", user_id=actor_id, resource_type="report", resource_id=str(report.id),
                    details={"prediction_id": str(prediction.id), "analysis_type": prediction.prediction_target})
    db.commit()
    db.refresh(report)
    return report


def render_report_pdf(report: Report) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    data = report.report_data or {}
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=18 * mm, bottomMargin=18 * mm, title=report.title,
                                 author="RiskSense AI")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RiskSenseTitle", parent=styles["Title"], textColor=colors.HexColor("#123B5D"),
                              alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#176B87"),
                              spaceBefore=10, spaceAfter=6))
    story = [Paragraph("RiskSense AI", styles["RiskSenseTitle"]), Paragraph(report.title, styles["Heading1"]),
             Spacer(1, 4 * mm)]
    details = [
        ("Patient reference", data.get("patient_reference")), ("Analysis", data.get("analysis_type")),
        ("Analysis date", data.get("analysis_at")), ("Model version", data.get("model_version")),
        ("Risk score", f"{float(data['risk_score']) * 100:.2f}%" if data.get("risk_score") is not None else "Not available"),
        ("Classification", data.get("risk_classification")),
    ]
    table = Table([[Paragraph(str(label), styles["BodyText"]), Paragraph(str(value or "Not available"), styles["BodyText"])]
                   for label, value in details], colWidths=[48 * mm, 105 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF4F7")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A7BEC8")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 6)]))
    story.extend([table, Paragraph("Result summary", styles["Section"]), Paragraph(report.summary or "No summary available.", styles["BodyText"])])
    snapshot = data.get("input_snapshot") or {}
    features = snapshot.get("features") or {}
    if features:
        story.extend([Paragraph("Historical inputs used", styles["Section"]),
                      Table([["Input", "Recorded value"]] + [[str(key), str(value)] for key, value in features.items()],
                            colWidths=[70 * mm, 83 * mm], style=TableStyle([
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176B87")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A7BEC8")),
                                ("PADDING", (0, 0), (-1, -1), 5)]))])
    sources = snapshot.get("sources") or {}
    dated = []
    for key, source in sources.items():
        if isinstance(source, dict):
            timestamp = source.get("measured_at") or source.get("recorded_at") or source.get("as_of") or source.get("updated_at")
            if timestamp:
                dated.append([str(key), str(timestamp)])
    if dated:
        story.extend([Paragraph("Measurement dates", styles["Section"]),
                      Table([["Input", "Date/time"]] + dated, colWidths=[70 * mm, 83 * mm],
                            style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176B87")),
                                              ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                              ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#A7BEC8")),
                                              ("PADDING", (0, 0), (-1, -1), 5)]))])
    story.extend([Spacer(1, 8 * mm), Paragraph("Decision-support disclaimer", styles["Section"]),
                  Paragraph(str(data.get("disclaimer") or DISCLAIMER), styles["BodyText"])])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5A6B73"))
        canvas.drawString(18 * mm, 10 * mm, "RiskSense AI - confidential patient report")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
