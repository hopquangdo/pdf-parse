"""Mô hình nghiệp vụ, không phụ thuộc thư viện ngoài."""
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Union

MEMBER_TYPES = ("L", "d", "Ф", "M")


def _num(v) -> float:
    if isinstance(v, bool):
        raise ValueError("không phải số")
    if isinstance(v, str):
        v = float(v.strip().replace(",", "."))
    return int(v) if float(v).is_integer() else float(v)


@dataclass
class Member:
    """Một dòng thống kê. L: thép góc, d: bản mã, Ф: thép tròn, M: bu lông."""
    section: str
    mark: Optional[str]
    type: str
    w: float
    t: Optional[Union[float, str]]
    len: float
    qty: int

    @classmethod
    def from_dict(cls, d: dict) -> "Member":
        """Ép kiểu số (model hay trả "50" hoặc "50,5"); lỗi thì raise ValueError/KeyError."""
        t = d.get("t")
        if t is not None and t != "Bộ":
            t = _num(t)
        return cls(str(d["section"]), d.get("mark"), d["type"], _num(d["w"]), t, _num(d["len"]), int(_num(d["qty"])))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Issue:
    level: str  # error | warning | info
    message: str
    mark: Optional[str] = None


@dataclass
class ExtractionJob:
    id: str
    status: str = "pending"  # pending | running | done | failed
    filename: str = ""
    rows: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    error: Optional[str] = None
    owner_id: str = ""  # the account that uploaded it; empty on drawings from before accounts existed (admin-only)
    page_count: int = 0
    created_at: float = 0.0
    usage: dict = field(default_factory=dict)  # LLM tokens / cost / time for this job
    drawing_type: str = "steel_column"  # which reader family handles it (see application/drawing_types)


@dataclass
class OcrTable:
    """One table found on a page, read as rows of cells (one Excel sheet)."""
    name: str
    rows: List[List[str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    flags: Dict[str, str] = field(default_factory=dict)      # "row,col" -> why a person should check that cell


@dataclass
class OcrPage:
    """One page of an OCR job: wait -> run -> done | error. A page can hold several tables."""
    page: int
    status: str = "wait"
    tables: List[OcrTable] = field(default_factory=list)
    error: str = ""
    cost_vnd: int = 0
    seconds: float = 0.0


@dataclass
class OcrJob:
    """A PDF whose chosen pages are read as tables and exported to Excel (one sheet per page)."""
    id: str
    filename: str
    owner_id: str = ""
    created_at: float = 0.0
    page_count: int = 0
    rotate: Union[int, str] = 0          # 0/90/180/270 or "auto"
    pages: List[OcrPage] = field(default_factory=list)

    @property
    def status(self) -> str:
        states = {p.status for p in self.pages}
        if states & {"wait", "run"}:
            return "running" if "run" in states or "done" in states or "error" in states else "pending"
        return "failed" if states == {"error"} else "done"
