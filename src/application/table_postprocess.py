"""Repair what a recognizer got wrong in a steel quantity table, from what the table itself must satisfy.

A recognizer reads each cell alone; the table as a whole obeys rules it cannot see: a column of numbers keeps one format, the unit
weight follows from the section ("L63x63x5" is 4,81 kg/m), "number x length = total", "total x unit weight = mass", the index runs
1, 2, 3. A cell that breaks a rule is repaired when the rules say what it must be, otherwise it is flagged for a person.
"""
import difflib
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from src.domain.numbers import parse_vn_number

Flags = Dict[Tuple[int, int], str]

# column keys of a quantity table, in the order such tables print them
ORDER = ("sl", "cd", "dt", "tong", "kl", "ds")          # count, length, unit weight, total length, mass, paint area
KEYWORDS = {"sl": ("số lượng", "so luong", "lượng (ck"), "kl": ("khối lượng", "t. lượng", "t.lượng"), "ds": ("diện tích sơn", "tích sơn")}
STEEL = 7.85                                             # kg per mm of thickness per m2

VOCAB = """thép tấm góc tròn ống hình bulon bu lông tăng đơ khóa cáp vòng đệm ma ní mạ kẽm chốt ốc ecu đai cột thang leo kim thu sét giằng bậc
trèo thân bản mã gân liên kết dây co vào gá chống xoay đế đèn báo không khối lượng tổng cộng đơn trọng vị số kích thước quy cách diện tích sơn ghi
chú loại thiết bị tận dụng đốt cũ bộ cái mm kg phụ kiện thống kê vật liệu tủ đỡ sàn thao tác khung định neo móng cầu hàng rào""".split()
_VOCAB_LOWER = sorted(set(VOCAB), key=len, reverse=True)


# ------------------------------------------------------------------ numbers
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


def normalise_number(text: str) -> Optional[str]:
    """A number as the table prints it ("0,020"), repairing separators read wrongly (0:020, 0;020, 0.020 -> 0,020);
    None when the cell is not a number even after the repair."""
    t = str(text).strip().replace(" ", "")
    if not t or t in ("-", "–"):
        return None
    t = re.sub(r"(?<=\d)[:;](?=\d)", ",", t)
    if re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+(,\d+)?", t):                 # 1.849,51 or 13.726
        return t
    if re.fullmatch(r"\d+\.\d+", t):                                 # 0.020 read with a point
        t = t.replace(".", ",")
    if re.fullmatch(r"[\dOolIS]+(,[\dOolIS]+)?", t) and re.search(r"\d", t):
        t = t.translate(_DIGIT_FIX)
    return t if re.fullmatch(r"\d+(,\d+)?", t) else None


def to_float(text) -> Optional[float]:
    if isinstance(text, (int, float)):
        return float(text)
    n = normalise_number(str(text))
    return None if n is None else parse_vn_number(n)


def fmt(value: float, like: str = "") -> str:
    """value printed with the decimals of `like` (or as many as it needs, at most 3), decimal comma."""
    d = len(like.split(",")[-1]) if "," in like else (2 if abs(value - round(value)) > 1e-9 else 0)
    return f"{value:.{min(d, 3)}f}".replace(".", ",")


# ------------------------------------------------------------------ unit weight from the section
def expected_unit_weight(spec: str, angles: Dict[str, float]) -> Optional[float]:
    """kg/m (angles, bars, tubes) or kg/m2 (plates) from the section text; None when it does not say enough."""
    s = str(spec).strip().replace(" ", "").replace("×", "x").replace("X", "x")
    m = re.match(r"^[LlĐ](\d{2,3})(?:x(\d{2,3}))?(?:x(\d{1,2}(?:,\d)?))?", s)
    if m and s[0] in "Ll":
        nums = [n for n in re.split(r"[x\-]", s[1:]) if re.fullmatch(r"\d+([.,]\d)?", n)]
        if len(nums) >= 2:
            w = int(nums[0])
            t = nums[2] if (len(nums) >= 3 and nums[0] == nums[1]) else nums[1]
            return angles.get(f"L{w}x{w}x{t.replace(',', '.')}")
        return None
    m = re.match(r"^[dđ]=?(\d+(?:[.,]\d)?)", s)
    if m:
        return round(STEEL * float(m.group(1).replace(",", ".")), 2)
    m = re.match(r"^[ØΦφ](\d+)(?:x(\d+(?:[.,]\d)?)(?:x(\d+))?)?", s)
    if m:
        d = int(m.group(1))
        t = float(m.group(2).replace(",", ".")) if m.group(2) else None
        if t is not None and t <= 10 and m.group(3):                 # Ø27x2,5x1000: a tube, wall 2,5
            return round((d - t) * t * 0.02466, 3)
        return round(d * d * math.pi / 4 * STEEL / 1000, 3)          # a round bar
    return None


# ------------------------------------------------------------------ columns
def find_header(rows: Sequence[Sequence[str]]) -> Optional[int]:
    for i, r in enumerate(rows[:4]):
        text = " ".join(str(c).lower() for c in r)
        if sum(w in text for w in ("số", "lượng", "stt", "quy cách", "khối", "trọng", "đơn")) >= 2 and sum(bool(str(c).strip()) for c in r) >= 3:
            return i
    return None


def locate_columns(header: Sequence[str]) -> Dict[str, int]:
    """Column index of sl, cd, dt, tong, kl, ds. The count column is found by its title; the others follow it in print order, which
    stays right when their titles are garbled."""
    low = [str(c).lower() for c in header]
    cols: Dict[str, int] = {}
    for key, words in KEYWORDS.items():
        hit = next((j for j, t in enumerate(low) if any(w in t for w in words)), None)
        if hit is not None:
            cols[key] = hit
    if "sl" in cols:
        for off, key in enumerate(ORDER[1:], 1):
            if cols["sl"] + off < len(header):
                cols.setdefault(key, cols["sl"] + off)
    if "kl" in cols and "tong" not in cols and cols["kl"] >= 1:
        cols["tong"] = cols["kl"] - 1
    return cols


def align_columns(rows: Sequence[Sequence[str]], h: int, cols: Dict[str, int]) -> Optional[Dict[str, int]]:
    """The column mapping, moved by up to two columns to where the arithmetic of the rows holds (a header drawn over one column more or
    less than the data would otherwise misplace every number). None when no placement makes at least two rows add up."""
    def holds(shift: int) -> int:
        n = 0
        for r in rows[h + 1:]:
            def v(key: str) -> Optional[float]:
                j = cols.get(key)
                return to_float(r[j + shift]) if j is not None and 0 <= j + shift < len(r) and str(r[j + shift]).strip() else None
            sl, cd, tong, dt, kl = v("sl"), v("cd"), v("tong"), v("dt"), v("kl")
            n += bool(None not in (sl, cd, tong) and tong > 0 and abs(sl * cd - tong) <= 0.05 * tong)
            n += bool(None not in (tong, dt, kl) and kl > 0 and abs(tong * dt - kl) <= 0.05 * kl)
        return n
    scores = {sh: holds(sh) for sh in (0, 1, -1, 2, -2)}
    best = max(scores, key=lambda k: (scores[k], -abs(k)))
    return {k: j + best for k, j in cols.items()} if scores[best] >= 2 else None


# ------------------------------------------------------------------ text
def fix_words(text: str) -> str:
    """Words that are one or two letters away from a word of the trade take its spelling (giăng -> giằng, LÓT/LỘT -> as printed)."""
    def word(m: re.Match) -> str:
        w = m.group(0)
        if len(w) < 5 or any(ch.isdigit() for ch in w):
            return w
        close = difflib.get_close_matches(w.lower(), _VOCAB_LOWER, 1, 0.78)
        if not close or close[0] == w.lower():
            return w
        c = close[0]
        return c.upper() if w.isupper() else c.capitalize() if w[0].isupper() else c
    return re.sub(r"[^\W\d_]+", word, text)


# ------------------------------------------------------------------ the repair
def repair(rows: List[List[str]], angles: Dict[str, float], tol: float = 0.08) -> Tuple[List[List[str]], Flags]:
    """The table with what the rules can fix fixed, and {(row, col): reason} for the cells a person should check."""
    rows = [list(map(str, r)) for r in rows]
    flags: Flags = {}
    h = find_header(rows)
    if h is None:
        return rows, flags
    cols = locate_columns(rows[h])
    cols = align_columns(rows, h, cols) or {}                # no placement of the numbers adds up: only the spelling is repaired
    def numeric_share(j: int) -> float:
        cells = [r[j].strip() for r in rows[h + 1:] if j < len(r) and r[j].strip() not in ("", "-")]
        return sum(to_float(c) is not None for c in cells) / len(cells) if cells else 0.0
    cols = {k: j for k, j in cols.items() if numeric_share(j) >= 0.6}      # a column of words (a unit, a note) is never a number column
    spec_col = next((j for j, t in enumerate(rows[h]) if "quy cách" in t.lower() or "kích thước" in t.lower()), None)
    body = range(h + 1, len(rows))
    numeric = {j for j in range(len(rows[h])) if j in cols.values() or j == 0}

    for i in body:                                           # 1. the format of every number column
        for j in sorted(cols.values()):
            if j < len(rows[i]) and rows[i][j].strip():
                n = normalise_number(rows[i][j])
                if n is None:
                    flags[(i, j)] = "không đọc thành số"
                else:
                    rows[i][j] = n

    def val(i: int, key: str) -> Optional[float]:
        j = cols.get(key)
        return to_float(rows[i][j]) if j is not None and j < len(rows[i]) and rows[i][j].strip() else None

    def put(i: int, key: str, x: float, why: str) -> None:
        j = cols[key]
        rows[i][j] = fmt(x, rows[i][j])
        flags[(i, j)] = why

    for i in body:                                           # 2. the rules between the numbers of a row
        spec = rows[i][spec_col] if spec_col is not None and spec_col < len(rows[i]) else ""
        want = expected_unit_weight(spec, angles) if spec else None
        raw = rows[i][cols["dt"]].strip() if "dt" in cols and cols["dt"] < len(rows[i]) else ""
        if want is not None and raw:                         # only a printed value is checked: a blank cell stays blank
            have = to_float(raw)
            if have is None or abs(have - want) > 0.03 * want:
                put(i, "dt", want, f"đơn trọng theo quy cách {spec}: {fmt(want)}")
        sl, cd, tong, dt, kl = val(i, "sl"), val(i, "cd"), val(i, "tong"), val(i, "dt"), val(i, "kl")
        if None not in (sl, cd, tong) and "tong" in cols and abs(sl * cd - tong) > tol * max(tong, 1e-9) and sl * cd > 0:
            put(i, "tong", sl * cd, f"tổng = số lượng × chiều dài = {fmt(sl * cd)}")
            tong = sl * cd
        if None not in (tong, dt, kl) and "kl" in cols and abs(tong * dt - kl) > tol * max(kl, 1e-9) and tong * dt > 0:
            put(i, "kl", tong * dt, f"khối lượng = tổng × đơn trọng = {fmt(tong * dt)}")

    prev = None                                              # 3. the index runs 1, 2, 3 (it may restart at 1 in a new group)
    for i in body:
        first = rows[i][0].strip() if rows[i] else ""
        if re.fullmatch(r"\d+", first):
            k = int(first)
            if prev is not None and k not in (prev + 1, 1):
                flags.setdefault((i, 0), f"STT {k} sau {prev}: có thể thiếu hoặc đọc sai một hàng")
            prev = k

    for i in body:                                           # 4. spelling of the words
        for j in range(len(rows[i])):
            if j not in numeric and rows[i][j] and re.search(r"[^\W\d_]{4,}", rows[i][j]):
                rows[i][j] = fix_words(rows[i][j])
    return rows, flags
