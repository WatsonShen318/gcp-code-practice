"""Build five fictional cases using the sandbox ZIP's reviewer-visible columns.

Offline only: no database, cloud SDK, credentials or network calls. To rebuild PDFs,
install reportlab in a development environment; it is not an app dependency.
"""
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "case.json"


def write_pdf(target, title, rows):
    target.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#181c2b")
    story = [Paragraph("SYNTHETIC DEMO - NO REAL PATIENT DATA", styles["Heading3"]),
             Spacer(1, 18), Paragraph(title, styles["Title"]), Spacer(1, 18)]
    for label, value in rows:
        story.extend([Paragraph(label, styles["Heading3"]), Paragraph(str(value), styles["BodyText"]), Spacer(1, 10)])
    story.extend([Spacer(1, 20), Paragraph("Fictional training material. Not a clinical recommendation or an actual medical record.", styles["Italic"])])
    SimpleDocTemplate(str(target), pagesize=(612, 792), rightMargin=48, leftMargin=48,
                      topMargin=36, bottomMargin=36, title=title, author="PA Caddie synthetic demo").build(story)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    # Preserve the existing engine's question definitions and demo drug options only.
    for key in ("cases", "mockClaimDefaults", "mockClaimResults", "caseNotes", "toolData"):
        data[key] = [] if key == "cases" else {}
    data["synthetic"] = True
    sources = []
    scenarios = [
        ("Continuation: weight reduction", "1982-04-12", 220, 198, "F", "F", False),
        ("Continuation: below weight threshold", "1976-06-08", 210, 205, "M", "F", False),
        ("Documentation missing", "1991-02-20", 240, 216, "F", "F", True),
        ("Quantity limit review", "1987-09-03", 200, 180, "M", "T", False),
        ("Age threshold review", "2010-12-15", 190, 171, "F", "F", False),
    ]
    for n, (scenario, dob, baseline, current, sex, over_limit, missing_docs) in enumerate(scenarios, 1):
        pa, name, member = f"26-90000000{n}", f"Synthetic Member {n:02}", f"DEMO-MEMBER-{n:03}"
        asof, drug, gpi, ndc = "2026-10-20T10:00:00", "WEGOVY 25MG OR TABS", "6125207000", "00169442531"
        age = 2026 - int(dob[:4]) - (dob[5:] > "10-20")
        loss = (baseline - current) / baseline * 100
        answers = {"1": "T", "2": "T" if age >= 18 else "F", "3": "T",
                   "4": "T" if loss >= 5 else "F", "5": "F" if missing_docs else "T", "6": over_limit}
        header = dict(prior_athzn_nbr=pa, mbr_acct_id=member, prior_athzn_drug_nm=drug,
                      prior_athzn_gpi_cd=gpi, gpi10_cd=gpi, pac_cd="DEMO-PAC", pac_desc="Weight management demo",
                      icd_dx_cd="DEMO", icd_dx_cd_desc="Fictional weight management scenario", urg_prior_athzn_ind=0,
                      rfrnc_nbr=f"DEMO-REF-{n:03}", qset_nbr="DEMO-QSET", qset_desc="Synthetic weight management criteria",
                      pag_nm="SYNTHETIC PLAN", dsply_pag_nm="SYNTHETIC PLAN", mbr_frst_nm="Synthetic",
                      mbr_last_nm=f"Member {n:02}", mbr_brth_dt=dob, mbr_gndr_cd=sex)
        submission = [dict(CRTE_DT=asof, RX_DESC_TXT=drug, RX_REP_NDC_NBR=ndc,
                           RX_QTY_NBR=60 if over_limit == "T" else 30, RX_DAYS_SPLY_NBR=30)]
        claims = [dict(FILL_DT=f"2026-{month:02}-15", CLM_STUS_CD="P", RVRSL_DT=None, DRUG_BRND_NM="WEGOVY",
                       DRUG_STRGH_NM="25MG", DSPNS_UNT_QTY=30, DAY_SPLY_QTY=30, GPI10_CD=gpi,
                       NCPDP_RJCT1_CD=None, PHMCY_NM="Synthetic Pharmacy") for month in (6, 7, 8, 9)]
        pa_history = [dict(prior_athzn_nbr=f"25-90000000{n}", prior_athzn_drug_nm=drug, gpi10_cd=gpi,
                           prior_athzn_crte_ts="2025-09-01", prior_athzn_rsltn_drvd_cd="APPROVAL",
                           prior_athzn_aprv_end_dt="2026-09-01", aprv_drtn_day_nbr=365, pac_cd="DEMO-PAC")]
        code = "75,76" if over_limit == "T" else "75"
        message = "Prior Authorization Required; Quantity limit exceeded" if over_limit == "T" else "Prior Authorization Required"
        mocks = [dict(CRTE_TS=asof, CRTE_BY_USER_ID="SYSTEM-DEMO", FILL_DT="2026-10-20", INITL_MOCK_IND="1",
                      MOCK_STUS_CD="REJECTED", RJCT_CD=code, RJCT_MSG_TXT=message, PHMCY_ID="DEMO-PHARMACY")]
        comment = f"Baseline 2026-04-15: {baseline} lb; current 2026-10-15: {current} lb. Synthetic example."
        doc_rows = [
            ("progress-note.pdf", "Synthetic progress note", [
                ("Member / PA", f"{name} | {member} | {pa}"), ("Date of birth / visit", f"{dob} | Visit: 2026-10-15"),
                ("Submitted therapy", drug), ("Treatment history", "Stable maintenance dose since 2026-06-15. Four synthetic paid fills recorded."),
                ("Lifestyle documentation", "Fictional diet and physical activity program documented."),
                ("Prescriber", "Demo Clinician - fictional provider")]),
            ("weight-record.pdf", "Synthetic weight record", [
                ("Member / PA", f"{name} | {member} | {pa}"), ("Baseline weight", f"{baseline} lb on 2026-04-15"),
                ("Current weight", f"{current} lb on 2026-10-15"), ("Calculated change", f"{loss:.1f}% loss from baseline"),
                ("Source", "Both measurements are invented for this demo."),
                ("Documentation status", "Weight record reported but attachment not supplied." if missing_docs else "Weight record attached for manual verification.")]),
        ]
        attachments = []
        for filename, title, rows in doc_rows:
            write_pdf(ROOT / "static" / "documents" / pa / filename, title, rows)
            if not (missing_docs and filename == "weight-record.pdf"):
                attachments.append(dict(ATCHM_ID=f"DEMO-{n}-{filename}", filename=filename,
                                        ATCHM_DESC=title, CRTE_TS=asof, CNTNT_TYP_CD="application/pdf",
                                        question_numbers=[3] if filename == "progress-note.pdf" else [4, 5]))
        raw = dict(synthetic=True, scenario=scenario, pa=pa, asof=asof, header=header,
                   qset=[dict(ordinal_nbr=int(q), qstn_txt=data["questionMetadata"][q]["f"], qstn_typ_cd="BOOLEAN",
                              true_rspns_cd=b["T"], false_rspns_cd=b["F"], score_val_nbr=0) for q, b in data["skipLogic"].items()],
                   submission=submission, prescriber_answers=[dict(ORDEAL_NBR=int(q), ANSWR_TXT="1" if a == "T" else "0",
                         EXTN_TXT=comment if q == "4" else None) for q, a in answers.items()],
                   initial_answers=answers, q_comments={"4": comment}, mock_claims=mocks,
                   pa_history=pa_history, claim_history=claims, attachments=attachments,
                   fallout=dict(step=1150, reason="Could not validate outcome code; manual criteria review required"))
        sources.append(raw)
        documents = [dict(a, url=f"/static/documents/{pa}/{a['filename']}") for a in attachments]
        case = dict(id=pa, scenario=scenario, synthetic=True, attachments=documents,
                    meta=dict(drug="Wegovy Tablet (semaglutide)", submittedDrug=drug, requestedDrug="Wegovy Tablet (semaglutide)",
                              cls="DEMO-PAC - Weight management demo", dx=header["icd_dx_cd_desc"], lob="Commercial", origin="ePA",
                              ref=header["rfrnc_nbr"], name=header["qset_desc"], client="SYNTHETIC PLAN", qset="DEMO-QSET", ndc=ndc, gpi=gpi, urgent=False),
                    member=dict(id=member, name=name, dob=f"{dob[5:7]}/{dob[8:]}/{dob[:4]}", sex="Female" if sex == "F" else "Male", pag="SYNTHETIC PLAN"),
                    claim=dict(code=code, msg=message, dt="2026-10-20", drug=drug, qty=f"{submission[0]['RX_QTY_NBR']} tablets", days="30"),
                    phNote="No active approved PA. One synthetic prior approval expired on 09/01/2026.",
                    legs=[dict(role="Technician", rev="DEMO-REVIEWER", aht="", ahtS=0, queue="Pending Approval", isAgent=False,
                               fallout="Synthetic ePA stopped at step 1150. Manual criteria review required.", initAns=answers,
                               comments={"4": comment}, notes={"2": f"DOB: {dob}. Age at case creation: {age} years.",
                                   "3": "Four synthetic paid fills from June through September 2026.",
                                   "5": "Weight documentation missing: request additional documentation." if missing_docs else "Progress note and weight record attached."},
                               docs={str(q): a["filename"] for a in attachments for q in a["question_numbers"]})])
        data["cases"].append(case)
        data["mockClaimDefaults"][pa] = dict(qty=str(submission[0]["RX_QTY_NBR"]), days="30", pharmacyId="DEMO-PHARMACY",
                                            fillDate="10/20/2026", physicianId="DEMO-PROVIDER", psc="0", drugName=drug, ndc=ndc)
        data["mockClaimResults"][pa] = {tab: dict(result=message, settlement="DEMO", code=code, label="PA Required" if code == "75" else "PA + Quantity Limit") for tab in ("msg", "d30", "d60", "d90")}
        data["toolData"][pa] = dict(paHistory=[dict(pa=pa, drug=drug, date="10/20/26", outcome=None),
                                              dict(pa=pa_history[0]["prior_athzn_nbr"], drug=drug, date="09/01/25", outcome="A")],
                                    claimHistory=[dict(dt=f"{m:02}/15/26", drug=drug, qty="30", days=30, status="Paid") for m in (9, 8, 7, 6)])
    # Do not carry the original case's evidence into any fictional case.
    for q in data["questionMetadata"].values():
        q.pop("ev", None)
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "data" / "synthetic-cases.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
