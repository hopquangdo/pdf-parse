"""A drawing type = one family of drawings with its own way of finding and reading the schedule.

Add a new family (a beam, an antenna mast...) by writing a class with `key`, `label` and `extract`, and registering it
in registry.py. The extraction service, API and UI stay as they are.
"""
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Sequence

from src.domain.models import Issue
from src.domain.ports import PageRenderer, TableLocator, TableReader, VisionReader


@dataclass
class ExtractionContext:
    pdf: bytes
    pages: Sequence[int]
    renderer: PageRenderer
    locator: TableLocator
    step: Callable[..., AbstractContextManager]                       # run-log step: `with ctx.step("name", **detail) as d`
    options: Dict = field(default_factory=dict)                       # rotate / cols / rows for generic reading
    workers: int = 6
    reader: Optional[VisionReader] = None                             # free-form page/region reader
    table_reader: Optional[TableReader] = None                        # primary reader of table crops
    review_reader: Optional[TableReader] = None                       # second, independent reader (+ zoomed re-reads)
    read_region: Optional[Callable] = None                            # retrying wrapper around `reader.read`
    run_parallel: Optional[Callable] = None                           # run_parallel(fn, items) -> [(result, error)] in order


@dataclass
class ExtractionOutcome:
    rows: List[dict] = field(default_factory=list)                    # raw row dicts; the service validates them
    issues: List[Issue] = field(default_factory=list)


class DrawingType(Protocol):
    key: str
    label: str

    def extract(self, ctx: ExtractionContext) -> ExtractionOutcome: ...
