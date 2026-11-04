"""The drawing types the product knows. Order = order shown to users; DEFAULT is used when none is chosen."""
from typing import Dict, List

from src.application.drawing_types.base import DrawingType
from src.application.drawing_types.generic import GenericRegions
from src.application.drawing_types.steel_column import SteelColumn

_TYPES: Dict[str, DrawingType] = {t.key: t for t in (SteelColumn(), GenericRegions())}
DEFAULT = "steel_column"


def get(key: str) -> DrawingType:
    try:
        return _TYPES[key]
    except KeyError:
        raise ValueError(f"unknown drawing type {key!r}; choose one of {sorted(_TYPES)}") from None


def available() -> List[dict]:
    return [{"key": t.key, "label": t.label, "default": t.key == DEFAULT} for t in _TYPES.values()]
