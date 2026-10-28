# Synthetic sandbox fixtures

All five cases and attachments are invented. No database, BigQuery, Spanner,
Secret Manager or real patient records were accessed to create them.

`synthetic-cases.json` uses the reviewer-visible column names from the uploaded
sandbox ZIP. `case.json` is the existing frontend's schemaVersion 2 presentation
format, generated from the same fictional values. The app continues to read
`case.json`; changing only `synthetic-cases.json` does not update the page.

| ZIP data section | Columns represented | Frontend |
| --- | --- | --- |
| `header` | `prior_athzn_nbr`, `mbr_acct_id`, `mbr_frst_nm`, `mbr_last_nm`, `mbr_brth_dt`, `mbr_gndr_cd`, `prior_athzn_drug_nm`, `prior_athzn_gpi_cd`, `gpi10_cd`, `pac_cd`, `pac_desc`, `icd_dx_cd`, `icd_dx_cd_desc`, `urg_prior_athzn_ind`, `rfrnc_nbr`, `qset_nbr`, `qset_desc`, `pag_nm`, `dsply_pag_nm` | Header, member details, PA information |
| `qset` | `ordinal_nbr`, `qstn_txt`, `qstn_typ_cd`, `true_rspns_cd`, `false_rspns_cd`, `score_val_nbr` | Question metadata and skip logic |
| `submission` | `CRTE_DT`, `RX_DESC_TXT`, `RX_REP_NDC_NBR`, `RX_QTY_NBR`, `RX_DAYS_SPLY_NBR` | Drug verification, mock claim inputs |
| `prescriber_answers` | `ORDEAL_NBR`, `ANSWR_TXT`, `EXTN_TXT` | `initial_answers`, `q_comments`, criteria review |
| `mock_claims` | `CRTE_TS`, `CRTE_BY_USER_ID`, `FILL_DT`, `INITL_MOCK_IND`, `MOCK_STUS_CD`, `RJCT_CD`, `RJCT_MSG_TXT`, `PHMCY_ID` | Sample claim response |
| `pa_history` | `prior_athzn_nbr`, `prior_athzn_drug_nm`, `gpi10_cd`, `prior_athzn_crte_ts`, `prior_athzn_rsltn_drvd_cd`, `prior_athzn_aprv_end_dt`, `aprv_drtn_day_nbr`, `pac_cd` | Previous PA history |
| `claim_history` | `FILL_DT`, `CLM_STUS_CD`, `RVRSL_DT`, `DRUG_BRND_NM`, `DRUG_STRGH_NM`, `DSPNS_UNT_QTY`, `DAY_SPLY_QTY`, `GPI10_CD`, `NCPDP_RJCT1_CD`, `PHMCY_NM` | Claim history and evidence |
| `attachments` | `ATCHM_ID`, `filename`, `ATCHM_DESC`, `CRTE_TS`, `CNTNT_TYP_CD` | PDF tabs and document details |
| `fallout` | `step`, `reason` | Manual review notice |

`question_numbers` and the local `url` are demo presentation fields associating
attachments with questions. They are not database columns. Every PDF contains a
synthetic-data notice. The missing-document case intentionally omits its weight
record from the attachment list. Opening a document does not verify a criterion.

Cases: weight reduction, insufficient weight reduction, missing weight record,
quantity limit review, and under-18 review. They illustrate UI branches, not
medical guidance. Current-case final decisions and real reviewer truth are not
part of these source fixtures.

To regenerate, use a development Python environment with `reportlab` installed:

```powershell
python scripts/build_synthetic_cases.py
```

The script writes both JSON files and PDFs in `static/documents/`. No PDF library
is required in the deployed container. Random Case draws from the five loaded
cases, excluding the current case, and cycles through the remaining cases before
refilling its pool. Each case retains its review state in the current browser
page; refreshing resets it. Export JSON downloads the current review, including
the filenames of opened documents. It does not save to an external system.
