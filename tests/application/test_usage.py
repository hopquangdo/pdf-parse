import json
import threading

from src.infrastructure.llm.usage import UsageLogger
from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.storage.local_storage import LocalStorage
from src.application.extraction_service import ExtractionService
from tests.conftest import PDF

PRICES = {"m/cheap": (1.0, None, 2.0), "m/cached": (1.0, 0.1, 2.0)}


def make(tmp_path=None):
    return UsageLogger(sink=(tmp_path / "u.jsonl") if tmp_path else None, usd_vnd=25000, pricing=PRICES)


def test_cost_from_price_table_in_usd_and_vnd():
    c = make().record(model="m/cheap", input_tokens=1000, output_tokens=500, seconds=1.5)
    assert c.cost_usd == (1000 * 1.0 + 500 * 2.0) / 1e6 and c.cost_vnd == round(c.cost_usd * 25000) and c.cost_source == "table"


def test_cached_tokens_use_the_cached_price():
    c = make().record(model="m/cached", input_tokens=1000, cached_tokens=800, output_tokens=0)
    assert abs(c.cost_usd - (200 * 1.0 + 800 * 0.1) / 1e6) < 1e-12


def test_provider_reported_cost_wins_and_unknown_model_is_n_a_not_guessed():
    lg = make()
    assert lg.record(model="m/cheap", input_tokens=1, provider_cost_usd=0.5).cost_usd == 0.5
    unknown = lg.record(model="who/knows", input_tokens=10, output_tokens=10)
    assert unknown.cost_usd is None and unknown.cost_vnd is None and "cost=n/a" in unknown.line()


def test_totals_by_scope_and_jsonl_sink(tmp_path):
    lg = make(tmp_path)
    with lg.scope("job1"):
        lg.record(model="m/cheap", input_tokens=1000, cached_tokens=100, output_tokens=100, seconds=2)
        lg.record(model="m/cheap", input_tokens=500, output_tokens=50, seconds=1)
        lg.record(model="who/knows", input_tokens=7)
    lg.record(model="m/cheap", input_tokens=99999)  # outside the scope
    t = lg.totals("job1")
    assert (t["calls"], t["input_tokens"], t["cached_tokens"], t["output_tokens"], t["unpriced_calls"]) == (3, 1507, 100, 150, 1)
    assert t["call_seconds"] == 3 and t["cost_vnd"] > 0 and "1 unpriced" in UsageLogger.format_totals(t)
    lines = (tmp_path / "u.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and json.loads(lines[0])["scope"] == "job1"


def test_thread_safe_recording():
    lg = make()
    ts = [threading.Thread(target=lambda: [lg.record(model="m/cheap", input_tokens=1) for _ in range(50)]) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert lg.totals("")["calls"] == 400


def test_extraction_job_stores_usage_even_when_reads_run_in_threads(tmp_path):
    lg = make()

    class BillingReader:
        def read(self, png, label):
            lg.record(model="m/cheap", label=label, input_tokens=100, output_tokens=10, seconds=0.2)
            return []

    svc = ExtractionService(BillingReader(), JsonJobRepo(tmp_path / "j"), LocalStorage(tmp_path / "f"), usage=lg)
    job = svc.create(PDF.read_bytes(), "a.pdf", drawing_type="generic")
    done = svc.run(job.id, cols=2, rows=2, pages=[1])
    assert done.usage["calls"] == 4 and done.usage["input_tokens"] == 400  # the scope reached every worker thread
    assert done.usage["cost_vnd"] > 0 and done.usage["wall_seconds"] >= 0
    assert svc.repo.get(job.id).usage["calls"] == 4  # persisted with the job
