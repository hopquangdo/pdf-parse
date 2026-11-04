from functools import lru_cache

from fastapi import APIRouter, Depends

from src import config
from src.application.drawing_types import registry
from src.infrastructure.excel.catalog import load_catalog
from .. import deps

router = APIRouter(prefix="/reference", tags=["reference"], dependencies=[Depends(deps.current_user)])


@lru_cache
def _catalog() -> dict:
    return load_catalog(config.TEMPLATE_XLSM)


@router.get("/catalog")
def catalog():
    """Steel/bolt unit weights and the paint factor, so the UI can evaluate the template's formulas live."""
    return _catalog()


@router.get("/drawing-types")
def drawing_types():
    """The families of drawings the product can read; the UI offers them on upload."""
    return registry.available()
