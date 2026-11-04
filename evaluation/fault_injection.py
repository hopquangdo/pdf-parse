"""Cài lỗi có kiểm soát vào bảng đúng để đo khả năng bắt lỗi của lớp review."""
import copy
import random
from typing import Dict, List, Tuple


def _swap_digits(n: int, rng: random.Random) -> int:
    s = list(str(n))
    if len(s) >= 2:
        i = rng.randrange(len(s) - 1)
        s[i], s[i + 1] = s[i + 1], s[i]
        if int("".join(s)) != n and s[0] != "0":
            return int("".join(s))
    return n + rng.choice([-1, 1, 10, -10])


def mutate(rows: List[Dict], kind: str, rng: random.Random) -> Tuple[List[Dict], Dict]:
    """Trả (bảng bị lỗi, mô tả lỗi). kind: digit_L | digit_a | qty | drop_row | dup_row | swap_L | mark."""
    out = copy.deepcopy(rows)
    i = rng.randrange(len(out))
    if kind in ("digit_L", "digit_a"):
        f = "L" if kind == "digit_L" else "a"
        old = out[i][f]
        out[i][f] = _swap_digits(old, rng)
        return out, {"kind": kind, "row": i, "mark": out[i]["mark"], "field": f, "old": old, "new": out[i][f]}
    if kind == "qty":
        old = out[i]["qty"]
        out[i]["qty"] = rng.choice([q for q in (1, 2, 4, 8, 16) if q != old])
        return out, {"kind": kind, "row": i, "mark": out[i]["mark"], "field": "qty", "old": old, "new": out[i]["qty"]}
    if kind == "drop_row":
        mark = out.pop(i)["mark"]
        return out, {"kind": kind, "row": i, "mark": mark}
    if kind == "dup_row":
        out.insert(i, copy.deepcopy(out[i]))
        return out, {"kind": kind, "row": i, "mark": out[i]["mark"]}
    if kind == "swap_L":
        j = (i + 1) % len(out)
        out[i]["L"], out[j]["L"] = out[j]["L"], out[i]["L"]
        return out, {"kind": kind, "row": i, "mark": out[i]["mark"], "other": out[j]["mark"]}
    if kind == "mark":
        old = out[i]["mark"]
        out[i]["mark"] = old[:-1] + ("1" if old[-1] != "1" else "7") if old[-1].isdigit() else old + "1"
        return out, {"kind": kind, "row": i, "mark": old, "new": out[i]["mark"]}
    raise ValueError(kind)


KINDS = ["digit_L", "digit_a", "qty", "drop_row", "dup_row", "swap_L", "mark"]
