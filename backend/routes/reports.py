from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response

from services import report_service
from services.rate_limit import limit_reports

router = APIRouter(prefix="/datasets", tags=["Reports"], dependencies=[Depends(limit_reports)])

NAME = Query(default="Dataset", max_length=80)
CURRENCY = Query(default="", max_length=1)
HTML_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"


@router.get("/{dataset_id}/download/clean.csv")
def download_clean_csv(dataset_id: str):
    content = report_service.clean_csv_bytes(dataset_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cleaned_dataset.csv"'},
    )


@router.get("/{dataset_id}/reports/html")
def report_html(dataset_id: str, name: str = NAME, currency: str = CURRENCY, download: bool = False):
    page = report_service.build_html(dataset_id, name, currency)
    disposition = "attachment" if download else "inline"
    return HTMLResponse(
        content=page,
        headers={
            "Content-Disposition": f'{disposition}; filename="analysis-report.html"',
            "Content-Security-Policy": HTML_CSP,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{dataset_id}/reports/pdf")
def report_pdf(dataset_id: str, name: str = NAME, currency: str = CURRENCY):
    pdf = report_service.build_pdf(dataset_id, name, currency)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="analysis-report.pdf"'},
    )