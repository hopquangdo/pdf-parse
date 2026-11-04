from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class RowIn(BaseModel):
    section: str
    mark: Optional[str] = None
    type: Literal["L", "d", "Ф", "M"]
    w: float = Field(gt=0)
    t: Optional[Union[float, str]] = None
    len: float = Field(gt=0)
    qty: int = Field(gt=0)


class ExportRequest(BaseModel):
    rows: List[RowIn]
    paint_factor: float = Field(default=1, ge=0, le=100)  # template cell P3 (hệ số sơn)
    job_id: Optional[str] = Field(default=None, pattern="^[0-9a-f]{12}$")  # run this export belongs to


class RowsUpdate(BaseModel):
    rows: List[RowIn]
