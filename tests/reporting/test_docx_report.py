from pathlib import Path
from src.reporting.site_report import SiteReportInput, generate_site_report


def test_site_report_writes_docx(tmp_path):
    out = generate_site_report(
        SiteReportInput(site_name="Test", bounds=(0, 0, 1, 1), mode="test"),
        output_dir=tmp_path,
        write_html=True,
        write_json=True,
        write_docx=True,
    )
    assert "docx" in out["paths"]
    assert Path(out["paths"]["docx"]).exists()
    assert Path(out["paths"]["docx"]).stat().st_size > 1000
