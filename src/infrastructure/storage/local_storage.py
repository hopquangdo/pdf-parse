"""Lưu file nhị phân (PDF, xlsm) trong thư mục cục bộ."""
import re
from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{12}\.(pdf|xlsm)", name):
            raise ValueError("Tên file không hợp lệ")
        return self.root / name

    def save(self, name: str, data: bytes) -> Path:
        p = self.path(name)
        p.write_bytes(data)
        return p

    def exists(self, name: str) -> bool:
        return self.path(name).exists()
