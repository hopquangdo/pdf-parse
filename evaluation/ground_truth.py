"""Run the whole extraction on a drawing and compare the rows with a ground-truth file, row by row.

  python -m evaluation.ground_truth [--pdf X.pdf] [--truth tests/fixtures/rows.json] [--type steel_column]

Needs LLM_API_KEY in .env. Prints what is missing, what is extra and which cells differ, plus tokens and cost.
"""
import argparse
import json
import tempfile
from pathlib import Path

from src import config
from src.application.extraction_service import ExtractionService
from src.infrastructure.persistence.json_job_repo import JsonJobRepo
from src.infrastructure.storage.local_storage import LocalStorage
from src.infrastructure.vision.openai_compat_reader import OpenAICompatReader
from src.infrastructure.vision.table_reader import TableVisionReader

FIELDS = ("section", "type", "w", "t", "len", "qty")


def compare(rows, truth):
    got = {(r["section"], r["mark"]): r for r in rows}
    want = {(r["section"], r["mark"]): r for r in truth}
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    wrong = [(k, f, want[k].get(f), got[k].get(f)) for k in want if k in got for f in FIELDS if want[k].get(f) != got[k].get(f)]
    return missing, extra, wrong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(config.ROOT / "3_-THAN-COT TD36m-2_66M_Hoa Tien Model (1).pdf"))
    ap.add_argument("--truth", default=str(config.ROOT / "tests" / "fixtures" / "rows.json"))
    ap.add_argument("--type", default="steel_column")
    a = ap.parse_args()
    import os
    key = os.environ["LLM_API_KEY"]
    with tempfile.TemporaryDirectory() as tmp:
        svc = ExtractionService(OpenAICompatReader(key), JsonJobRepo(Path(tmp) / "j"), LocalStorage(Path(tmp) / "f"),
                                table_reader=TableVisionReader(key, config.LLM_MODEL_NAME),
                                review_reader=TableVisionReader(key, config.LLM_REVIEW_MODEL))
        job = svc.create(Path(a.pdf).read_bytes(), Path(a.pdf).name, drawing_type=a.type)
        job = svc.run(job.id)
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))
    missing, extra, wrong = compare(job.rows, truth)
    n = len(truth)
    print(f"status={job.status} rows={len(job.rows)}/{n} missing={len(missing)} extra={len(extra)} wrong_cells={len(wrong)}")
    print("exact rows:", n - len({k for k, *_ in wrong}) - len(missing), "of", n)
    print("MISSING", missing)
    print("EXTRA", extra)
    for w in wrong:
        print("WRONG", w)
    for i in job.issues:
        print("ISSUE", i.level, i.message[:140])
    print("USAGE", job.usage)


if __name__ == "__main__":
    main()
