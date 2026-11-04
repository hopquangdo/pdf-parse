import io

import openpyxl
from PIL import Image

from app.api import deps
from app.main import app
from src.application.ocr_service import OcrService
from tests.application.test_ocr_service import FakeTableReader
from tests.conftest import PDF


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buf, "PNG")
    return buf.getvalue()


def use(answers):
    app.dependency_overrides[deps.ocr_service] = lambda: OcrService(FakeTableReader(answers))


def test_ocr_requires_sign_in(anon):
    assert anon.post("/ocr/text", files={"file": ("a.png", png_bytes(), "image/png")}).status_code == 401


def test_text_endpoint(client):
    use([{"text": "xin chào"}])
    try:
        r = client.post("/ocr/text", files={"file": ("a.png", png_bytes(), "image/png")})
    finally:
        app.dependency_overrides.pop(deps.ocr_service, None)
    assert r.status_code == 200 and r.json()["text"] == "xin chào"


def test_table_json_and_excel_download(client):
    rows = {"rows": [["STT", "KL"], ["1", "2,50"]]}
    use([rows, rows])
    try:
        j = client.post("/ocr/table", files={"file": ("bang.png", png_bytes(), "image/png")}).json()
        x = client.post("/ocr/table?format=xlsx", files={"file": ("bảng khối lượng.png", png_bytes(), "image/png")})
    finally:
        app.dependency_overrides.pop(deps.ocr_service, None)
    assert j["rows"] == rows["rows"] and j["columns"] == 2 and j["warnings"] == []
    assert x.status_code == 200 and "b%E1%BA%A3ng" in x.headers["content-disposition"] and x.headers["content-disposition"].endswith(".xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(x.content)).active
    assert ws["A1"].value == "STT" and ws["B2"].value == 2.5


def test_pdf_page_and_bad_input(client):
    use([{"text": "trang 1"}])
    try:
        ok = client.post("/ocr/text", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}, data={"page": "1"})
        bad_page = client.post("/ocr/text", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}, data={"page": "99"})
        not_image = client.post("/ocr/text", files={"file": ("a.txt", b"hello", "text/plain")})
        bad_rotate = client.post("/ocr/text", files={"file": ("a.png", png_bytes(), "image/png")}, data={"rotate": "45"})
    finally:
        app.dependency_overrides.pop(deps.ocr_service, None)
    assert ok.status_code == 200 and ok.json()["text"] == "trang 1"
    assert bad_page.status_code == 422 and not_image.status_code == 422 and bad_rotate.status_code == 422


def test_columns_hint_is_validated_and_sent_to_the_model(client):
    reader = FakeTableReader([{"rows": [{"STT": "1", "Tên": "Thép"}, {"Tên": "Bu lông", "STT": "2"}]}])
    app.dependency_overrides[deps.ocr_service] = lambda: OcrService(reader)
    try:
        ok = client.post("/ocr/table", files={"file": ("a.png", png_bytes(), "image/png")}, data={"columns": '["STT", "Tên"]'})
        bad = client.post("/ocr/table", files={"file": ("a.png", png_bytes(), "image/png")}, data={"columns": "not json"})
    finally:
        app.dependency_overrides.pop(deps.ocr_service, None)
    assert ok.status_code == 200 and '["STT", "Tên"]' in reader.prompts[0][1]
    assert ok.json()["rows"] == [["STT", "Tên"], ["1", "Thép"], ["2", "Bu lông"]]      # header once, cells in column order
    assert bad.status_code == 422


def test_ocr_job_runs_in_background_and_shows_in_history(client):
    rows = {"rows": [["STT", "KL"], ["1", "2,50"]]}
    use([rows] * 40)
    try:
        r = client.post("/ocr/jobs", data={"pages": "1-2"}, files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")})
        bad = client.post("/ocr/jobs", data={"pages": "99"}, files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")})
        assert r.status_code == 202 and bad.status_code == 422
        job = client.get(f"/ocr/jobs/{r.json()['id']}").json()          # background tasks have finished under TestClient
        x = client.get(f"/ocr/jobs/{job['id']}/xlsx")
        hist = client.get("/history").json()
    finally:
        app.dependency_overrides.pop(deps.ocr_service, None)
    assert job["status"] == "done" and [p["page"] for p in job["pages"]] == [1, 2] and job["pages"][0]["tables"][0]["rows"][1] == ["1", "2,50"]
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames[0].startswith("Trang 1") and any(n.startswith("Trang 2") for n in wb.sheetnames)   # a page with several tables gives a sheet each
    assert len(set(wb.sheetnames)) == len(wb.sheetnames)
    assert any(h["kind"] == "ocr" and h["id"] == job["id"] and h["rows"] >= 2 for h in hist)
