"""Declarative base for all tables."""
import uuid

from sqlalchemy.orm import DeclarativeBase


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass
