"""Create a finished demo run (job + run log) so the UI can be viewed without calling a model. Development only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.domain.models import Issue  # noqa: E402
from src.infrastructure.llm.usage import UsageLogger  # noqa: E402
from src.infrastructure.persistence.json_job_repo import JsonJobRepo  # noqa: E402
from src.infrastructure.runs.run_log import RunLog  # noqa: E402
from src.infrastructure.storage.local_storage import LocalStorage  # noqa: E402
from src.services.extraction_service import ExtractionService  # noqa: E402

usage = UsageLogger(usd_vnd=config.USD_VND)
runs = RunLog(config.DATA_DIR / "runs")
svc = ExtractionService(None, JsonJobRepo(config.DATA_DIR / "jobs"), LocalStorage(config.DATA_DIR / "files"), usage=usage, runs=runs)
pdf = (ROOT / "3_-THAN-COT TD36m-2_66M_Hoa Tien Model (1).pdf").read_bytes()
job = svc.create(pdf, "THAN-COT TD36m-2_66M_Hoa Tien Model.pdf")
job.rows = json.loads((ROOT / "tests" / "fixtures" / "rows.json").read_text(encoding="utf-8"))
job.issues = [Issue("warning", "L=1494 nhưng a+b+2c=1484: kiểm tra lại a (bản vẽ ghi 889, mặt cắt ghi 899)", "C16"),
              Issue("warning", "L=1494 nhưng a+b+2c=1484: kiểm tra lại a", "C17")]

# A believable run: two models (read + re-read), costs from the provider.
runs.begin(job.id, {"rotate": 90, "cols": 1, "rows": 1, "pages": "all"})
with usage.scope(job.id):
    with runs.step(job.id, "read_regions", regions=2):
        usage.record(model="deepseek/deepseek-v4-flash-vision-exp", label="table p6", input_tokens=1160, output_tokens=2503, seconds=6.5, provider_cost_usd=0.0019)
        usage.record(model="deepseek/deepseek-v4-flash-vision-exp", label="table p8", input_tokens=1160, output_tokens=2400, seconds=6.1, provider_cost_usd=0.0018)
    with runs.step(job.id, "review_rows", suspects=3):
        for k in range(3):
            usage.record(model="deepseek/deepseek-v4.1-flash", label=f"row{k}@400dpi", input_tokens=700, output_tokens=420, seconds=4.8, provider_cost_usd=0.00044)
job.usage = {**usage.totals(job.id), "wall_seconds": 41.2}
job.status = "done"
svc.repo.save(job)
runs.finish(job.id, status="done", error=None, rows=len(job.rows), issues=len(job.issues))
print(job.id)
