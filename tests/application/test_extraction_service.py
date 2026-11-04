from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.storage.local_storage import LocalStorage
from src.infrastructure.vision.fake_reader import FakeReader
from src.application.extraction_service import ExtractionService
from tests.conftest import PDF


def row(mark, qty=1):
    return {"section": "ĐOẠN B", "mark": mark, "type": "L", "w": 50, "t": 5, "len": 100, "qty": qty}


def make(tmp_path, reader, workers=6):
    svc = ExtractionService(reader, JsonJobRepo(tmp_path / "j"), LocalStorage(tmp_path / "f"), workers=workers, backoff=0)
    return svc, svc.create(PDF.read_bytes(), "a.pdf", drawing_type="generic")


def test_parallel_is_faster_and_keeps_order(tmp_path):
    # 4 vùng của trang 1, đọc cùng lúc
    labels = [f"p1_r{r}c{c}" for r in range(2) for c in range(2)]
    reader = FakeReader(by_label={l: [row(f"B{i}")] for i, l in enumerate(labels)}, delay=0.3)
    svc, job = make(tmp_path, reader, workers=4)
    done = svc.run(job.id, cols=2, rows=2, pages=[1])
    assert done.status == "done"
    assert [r["mark"] for r in done.rows] == ["B0", "B1", "B2", "B3"]  # đúng thứ tự vùng
    assert reader.max_active == 4  # 4 vùng đọc cùng lúc, không tuần tự


def test_one_failing_tile_does_not_break_job(tmp_path):
    reader = FakeReader(by_label={"p1_r0c0": [row("B1")], "p1_r0c1": RuntimeError("429")})
    svc, job = make(tmp_path, reader)
    done = svc.run(job.id, cols=2, rows=1, pages=[1])
    assert done.status == "done" and [r["mark"] for r in done.rows] == ["B1"]
    assert any("p1_r0c1" in i.message and i.level == "error" for i in done.issues)


def test_overlap_duplicates_removed_deterministically(tmp_path):
    reader = FakeReader(by_label={"p1_r0c0": [row("B1", 4)], "p1_r0c1": [row("B1", 4), row("B2")]})
    svc, job = make(tmp_path, reader)
    done = svc.run(job.id, cols=2, rows=1, pages=[1])
    assert [(r["mark"], r["qty"]) for r in done.rows] == [("B1", 4), ("B2", 1)]


def test_retry_then_success(tmp_path):
    class Flaky(FakeReader):
        n = 0
        def read(self, png, label):
            Flaky.n += 1
            if Flaky.n < 3:
                raise RuntimeError("timeout")
            return [row("B1")]
    svc, job = make(tmp_path, Flaky())
    done = svc.run(job.id, pages=[1])
    assert [r["mark"] for r in done.rows] == ["B1"] and not [i for i in done.issues if i.level == "error"]
