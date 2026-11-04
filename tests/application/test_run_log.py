import hashlib

from src.infrastructure.llm.usage import UsageLogger
from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.runs.run_log import RunLog
from src.infrastructure.storage.local_storage import LocalStorage
from src.application.extraction_service import ExtractionService
from tests.conftest import PDF

PRICES = {"m/read": (1.0, None, 2.0), "m/other": (2.0, None, 4.0)}


class BillingReader:
    """Bills two different models per region, like a real run that mixes models."""

    def __init__(self, usage):
        self.usage = usage

    def read(self, png, label):
        self.usage.record(model="m/read", label=label, input_tokens=1000, output_tokens=100, seconds=0.5)
        self.usage.record(model="m/other", label=label + "-check", input_tokens=500, cached_tokens=100, output_tokens=50, seconds=0.25)
        return [{"section": "B", "mark": "B" + label.replace("_", ""), "type": "L", "w": 50, "t": 5, "len": 100, "qty": 1}]


def make(tmp_path):
    usage = UsageLogger(usd_vnd=25000, pricing=PRICES)
    runs = RunLog(tmp_path / "runs")
    svc = ExtractionService(BillingReader(usage), JsonJobRepo(tmp_path / "j"), LocalStorage(tmp_path / "f"),
                            usage=usage, runs=runs, backoff=0)
    return svc, runs, usage


def test_run_file_records_input_options_steps_calls_totals(tmp_path):
    svc, runs, _ = make(tmp_path)
    pdf = PDF.read_bytes()
    job = svc.create(pdf, "bản vẽ.pdf", drawing_type="generic")
    assert runs.get(job.id)["status"] == "pending"
    svc.run(job.id, rotate=90, cols=2, rows=1, pages=[1, 2])
    r = runs.get(job.id)

    assert r["status"] == "done" and r["error"] is None
    assert r["input"]["filename"] == "bản vẽ.pdf" and r["input"]["size_bytes"] == len(pdf)
    assert r["input"]["sha256"] == hashlib.sha256(pdf).hexdigest() and r["input"]["pages"] == 8
    assert r["input"]["options"] == {"drawing_type": "generic", "rotate": 90, "cols": 2, "rows": 1, "pages": [1, 2]}

    assert [s["name"] for s in r["steps"]] == ["load_pdf", "render_regions", "read_regions", "validate"]
    assert all(s["status"] == "done" and s["seconds"] is not None for s in r["steps"])
    assert r["steps"][1]["detail"]["regions"] == 4 and r["steps"][3]["detail"]["rows"] == 4

    assert len(r["calls"]) == 8 and {c["step"] for c in r["calls"]} == {"read_regions"}  # calls are filed under their step
    assert {c["model"] for c in r["calls"]} == {"m/read", "m/other"}
    t = r["totals"]
    assert t["calls"] == 8 and t["input_tokens"] == 4 * 1500 and t["cached_tokens"] == 4 * 100 and t["output_tokens"] == 4 * 150
    read_usd = 4 * (1000 * 1.0 + 100 * 2.0) / 1e6
    other_usd = 4 * (500 * 2.0 + 50 * 4.0) / 1e6
    assert abs(t["by_model"]["m/read"]["cost_usd"] - read_usd) < 1e-9 and t["by_model"]["m/read"]["calls"] == 4
    assert abs(t["by_model"]["m/other"]["cost_usd"] - other_usd) < 1e-9
    assert abs(r["cost_usd"] - (read_usd + other_usd)) < 1e-9 and r["cost_vnd"] == t["cost_vnd"] > 0
    assert t["by_step"]["read_regions"]["calls"] == 8 and r["models"] == ["m/other", "m/read"]
    assert r["wall_seconds"] is not None and r["rows"] == 4


def test_a_failed_run_is_logged_with_the_failing_step(tmp_path):
    svc, runs, _ = make(tmp_path)
    job = svc.create(PDF.read_bytes(), "x.pdf", drawing_type="generic")
    svc.storage.path(f"{job.id}.pdf").unlink()  # the stored input disappears
    svc.run(job.id)
    r = runs.get(job.id)
    assert r["status"] == "failed" and r["error"]
    assert r["steps"][0]["name"] == "load_pdf" and r["steps"][0]["status"] == "failed"
    assert "FileNotFoundError" in r["steps"][0]["detail"]["error"]


def test_listing_reads_the_run_files_and_survives_a_damaged_one(tmp_path):
    svc, runs, _ = make(tmp_path)
    a = svc.create(PDF.read_bytes(), "a.pdf", drawing_type="generic")
    b = svc.create(PDF.read_bytes(), "b.pdf", drawing_type="generic")
    svc.run(a.id, pages=[1])
    (runs.root / "deadbeef0000.json").write_text("{not json", encoding="utf-8")
    listing = runs.list()
    assert [x["id"] for x in listing] == [b.id, a.id]  # newest first, damaged file skipped
    done = next(x for x in listing if x["id"] == a.id)
    assert done["status"] == "done" and done["page_count"] == 8 and done["cost_vnd"] > 0 and done["wall_seconds"] is not None
    assert set(done) == {"id", "owner_id", "filename", "status", "page_count", "created_at", "rows", "issues", "cost_usd", "cost_vnd", "wall_seconds"}


def test_export_output_is_logged_and_api_serves_list_and_run(client, rows):
    jid = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    exp = client.post("/exports", json={"rows": rows, "paint_factor": 1.5, "job_id": jid}).json()
    run = client.get(f"/extractions/{jid}/run").json()
    assert run["outputs"][0]["kind"] == "xlsm" and run["outputs"][0]["export_id"] == exp["id"]
    assert run["outputs"][0]["paint_factor"] == 1.5 and run["outputs"][0]["rows"] == 54
    assert run["input"]["filename"] == "a.pdf" and [s["name"] for s in run["steps"]][-1] == "validate"
    listing = client.get("/extractions").json()
    assert listing[0]["id"] == jid and listing[0]["status"] == "done"
    assert client.get("/extractions/000000000000/run").status_code == 404
    assert client.post("/exports", json={"rows": rows, "job_id": "../bad"}).status_code == 422


def test_saving_rows_updates_the_counts_in_the_run(client, rows):
    jid = client.post("/extractions", files={"file": ("a.pdf", PDF.read_bytes(), "application/pdf")}).json()["id"]
    client.put(f"/extractions/{jid}/rows", json={"rows": rows})
    assert client.get("/extractions").json()[0]["rows"] == 54
