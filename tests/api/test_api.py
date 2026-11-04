import io

import openpyxl

from tests.conftest import PDF


def test_export_roundtrip_keeps_macro_and_rows(client, rows, tmp_path):
    r = client.post("/exports", json={"rows": rows})
    assert r.status_code == 201
    body = r.json()
    assert body["rows"] == 54 and abs(body["expected_mass_kg"] - 1117.4) < 1.0
    d = client.get(body["download_url"])
    assert d.status_code == 200
    p = tmp_path / "out.xlsm"
    p.write_bytes(d.content)
    wb = openpyxl.load_workbook(p, keep_vba=True)
    assert wb.vba_archive is not None
    ws = wb["THAN COT 36M K CO GIA"]
    assert ws["C4"].value == "B1" and ws["G4"].value == 3900
    assert ws["A58"].value == "Tổng cộng" and ws["M58"].value == "=SUBTOTAL(9,M4:M57)"


def test_export_rejects_duplicate_marks(client, rows):
    assert client.post("/exports", json={"rows": [rows[0], rows[0]]}).status_code == 422


def test_export_rejects_bad_type(client, rows):
    assert client.post("/exports", json={"rows": [{**rows[0], "type": "Z"}]}).status_code == 422


def test_download_unknown_and_traversal(client):
    assert client.get("/exports/nope").status_code == 404
    assert client.get("/exports/..%2Fsecret").status_code == 404


def test_extraction_flow_with_fake_reader(client, rows):
    r = client.post("/extractions?rotate=90", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")})
    assert r.status_code == 202
    job = client.get(r.json()["status_url"]).json()  # background task đã chạy xong trong TestClient
    assert job["status"] == "done"
    assert job["rows"][0]["mark"] == "B1"
    upd = client.put(f"/extractions/{job['id']}/rows", json={"rows": rows})
    assert upd.status_code == 200 and len(upd.json()["rows"]) == 54 and upd.json()["issues"] == []


def test_extraction_rejects_non_pdf(client):
    assert client.post("/extractions", files={"file": ("a.pdf", b"hello", "application/pdf")}).status_code == 400


def test_extraction_unknown_job(client):
    assert client.get("/extractions/000000000000").status_code == 404


def test_get_and_put_work_without_llm_key(client, rows, monkeypatch):
    from app.api import deps
    from app.main import app
    job_id = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    app.dependency_overrides.pop(deps.extraction_service)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get(f"/extractions/{job_id}").status_code == 200
    assert client.put(f"/extractions/{job_id}/rows", json={"rows": rows}).status_code == 200
    assert client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).status_code == 503


def test_upload_too_large(client, monkeypatch):
    from src import config
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    assert client.post("/extractions", files={"file": ("a.pdf", b"%PDF" + b"x" * 10, "application/pdf")}).status_code == 413


def test_list_page_image_and_static_ui(client):
    jid = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    lst = client.get("/extractions").json()
    assert lst[0]["id"] == jid and lst[0]["page_count"] == 8
    img = client.get(f"/extractions/{jid}/pages/2.png?dpi=60&rotate=90")
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    assert client.get(f"/extractions/{jid}/pages/99.png").status_code == 422
    assert client.get("/app/").status_code in (200, 404)  # 404 nếu chưa có giao diện


def test_exported_rows_are_visible_and_view_starts_at_top(client, rows, tmp_path):
    """Mẫu gốc ẩn dòng 4-147 và mở ở dòng 220: file xuất ra phải thấy ngay các dòng dữ liệu."""
    body = client.post("/exports", json={"rows": rows}).json()
    p = tmp_path / "v.xlsm"
    p.write_bytes(client.get(body["download_url"]).content)
    wb = openpyxl.load_workbook(p, keep_vba=True)
    for name in ("THAN COT 36M K CO GIA", "THAN COT 36M"):
        ws = wb[name]
        assert not [r for r in range(4, 59) if ws.row_dimensions[r].hidden], name
        assert ws.freeze_panes == "A4" and ws.sheet_view.pane.ySplit == 3, name
        assert ws.sheet_view.pane.topLeftCell == "A4", name


def test_source_pdf_is_served_for_canvas_viewer(client):
    jid = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    r = client.get(f"/extractions/{jid}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert client.get("/extractions/000000000000/file").status_code == 404


def test_reference_catalog_comes_from_the_template(client):
    cat = client.get("/reference/catalog").json()
    assert cat["angles"]["L50x50x5"] == 3.77 and cat["angles"]["L100x100x8"] == 12.2
    assert len(cat["angles"]) > 90
    assert cat["bolts"]["M16"]["50"] > 0 and cat["paint_factor"] == 1


def test_paint_factor_is_written_to_cell_p3_of_both_sheets(client, rows, tmp_path):
    body = client.post("/exports", json={"rows": rows, "paint_factor": 2.5}).json()
    p = tmp_path / "pf.xlsm"
    p.write_bytes(client.get(body["download_url"]).content)
    wb = openpyxl.load_workbook(p, keep_vba=True)
    assert wb["THAN COT 36M K CO GIA"]["P3"].value == 2.5 and wb["THAN COT 36M"]["P3"].value == 2.5
    assert client.post("/exports", json={"rows": rows, "paint_factor": -1}).status_code == 422
    default = client.post("/exports", json={"rows": rows}).json()
    p.write_bytes(client.get(default["download_url"]).content)
    assert openpyxl.load_workbook(p, keep_vba=True)["THAN COT 36M"]["P3"].value == 1


def test_download_is_named_after_the_drawing_with_only_the_extension_changed(client, rows):
    from urllib.parse import quote, unquote

    def disposition(query: str) -> str:
        url = client.post("/exports", json={"rows": rows}).json()["download_url"]
        return unquote(client.get(f"{url}{query}").headers["content-disposition"]).rstrip('"')

    assert disposition(f"?name={quote('THAN-COT TD36m Hoa Tien Model.pdf')}").endswith("THAN-COT TD36m Hoa Tien Model.xlsm")
    assert disposition("").endswith("THONG KE THAN COT.xlsm")
    evil = disposition(f"?name={quote('../../etc/passwd.pdf')}")
    assert evil.endswith("passwd.xlsm") and ".." not in evil and "/" not in evil.split("filename")[1]
    assert disposition(f"?name={quote('ĐOẠN B.pdf')}").endswith("ĐOẠN B.xlsm")  # unicode survives


def test_catalog_uses_the_first_match_for_repeated_keys_like_vlookup(client):
    cat = client.get("/reference/catalog").json()["angles"]
    assert cat["L40x40x3"] == 1.35 and cat["L40x40x4"] == 2.42  # first rows of Steel Lib, not the later duplicates
