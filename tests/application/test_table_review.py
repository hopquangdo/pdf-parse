import copy
import json
import random

import pytest

from src.domain.table_rules import normalize_row
from evaluation.fault_injection import KINDS, mutate
from src.application.table_review.graph import TableReviewer
from tests.conftest import FIX

TRUTH = json.loads((FIX / "tables_truth.json").read_text(encoding="utf-8"))
P6 = [normalize_row(r) for r in TRUTH["6"]]
P8 = [normalize_row(r) for r in TRUTH["8"]]


def review_table(a, b, expected, rereader, max_attempts=3):
    return TableReviewer(rereader, max_attempts=max_attempts).review(a, b, expected)


class PerfectReader:
    """Đọc lại luôn đúng theo đáp án; đếm số lần gọi."""
    def __init__(self, truth):
        self.truth, self.calls = truth, []

    def __call__(self, idx, attempt):
        self.calls.append((idx, attempt))
        return copy.deepcopy(self.truth[idx])


def test_clean_table_makes_no_extra_calls():
    rr = PerfectReader(P6)
    out = review_table(copy.deepcopy(P6), copy.deepcopy(P6), len(P6), rr)
    assert rr.calls == [] and out.rows == P6
    assert {r.status for r in out.report} == {"ok"}


@pytest.mark.parametrize("kind", KINDS)
def test_single_fault_in_reader_a_is_corrected(kind):
    for seed in range(5):
        a, fault = mutate(P6, kind, random.Random(seed))
        rr = PerfectReader(P6)
        out = review_table(a, copy.deepcopy(P6), len(P6), rr)
        assert out.rows == P6, (kind, seed, fault)
        assert not [r for r in out.report if r.status == "human"], (kind, seed, fault)


def test_only_suspect_rows_are_reread():
    a, fault = mutate(P6, "digit_L", random.Random(1))
    rr = PerfectReader(P6)
    review_table(a, copy.deepcopy(P6), len(P6), rr)
    assert {i for i, _ in rr.calls} == {fault["row"]}


def test_agreeing_readers_but_bad_formula_goes_to_human_without_looping():
    rr = PerfectReader(P8)  # C16/C17 trong đáp án in sẵn a=889 nên sai công thức
    out = review_table(copy.deepcopy(P8), copy.deepcopy(P8), len(P8), rr)
    human = [r for r in out.report if r.status == "human"]
    assert [r.mark for r in human] == ["C16", "C17"]
    assert out.attempts == 1  # đọc lại cùng ảnh không đổi được kết quả nên không lặp


def test_garbage_reread_loops_then_escalates():
    a, fault = mutate(P6, "digit_L", random.Random(2))
    i = fault["row"]
    n = {"k": 0}

    def noisy(idx, attempt):
        n["k"] += 1
        row = copy.deepcopy(P6[idx])
        row["L"] = 9000 + attempt  # mỗi lần đọc một giá trị khác nhau
        return row

    out = review_table(a, copy.deepcopy(P6), len(P6), noisy, max_attempts=3)
    assert out.report[i].status == "human" and out.attempts == 3 and n["k"] == 3


def test_row_count_mismatch_flags_table():
    out = review_table(P6[:-3], P6[:-2], len(P6), PerfectReader(P6))
    assert out.table_flag and out.rows == []


def test_same_wrong_value_in_both_readers_only_caught_by_formula():
    a, fault = mutate(P6, "digit_L", random.Random(3))
    b = copy.deepcopy(a)  # hai reader cùng sai một kiểu
    out = review_table(a, b, len(P6), PerfectReader(P6))
    assert out.rows == P6  # công thức bắt được chỗ L lệch, đọc lại sửa
    a, fault = mutate(P6, "qty", random.Random(3))
    out = review_table(a, copy.deepcopy(a), len(P6), PerfectReader(P6))
    assert out.rows != P6  # GIỚI HẠN: qty sai ở cả hai reader thì không có gì để bắt
