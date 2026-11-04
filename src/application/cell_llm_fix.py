"""Re-read the few cells the recognizer was unsure of with a language model, all in one request.

The cells are cut out and stacked into one numbered contact sheet, so one call fixes dozens of cells and the model sees each cell
alone (it cannot re-read the whole table and repeat its first mistake).
"""
import io
from typing import Dict, List, Sequence, Set, Tuple

from PIL import Image, ImageDraw, ImageFont

from src.domain.ports import TableReader
from src.infrastructure.prompts import load_prompt

Pos = Tuple[int, int]
ROW_H, MAX_W = 56, 1500


def contact_sheet(pieces: Sequence[Image.Image]) -> bytes:
    """One numbered row per cell, scaled to a common height."""
    font = ImageFont.load_default(size=30)
    rows = []
    for k, piece in enumerate(pieces, 1):
        w = max(1, round(piece.width * ROW_H / max(1, piece.height)))
        rows.append(piece.convert("RGB").resize((min(w, MAX_W - 90), ROW_H), Image.LANCZOS))
    sheet = Image.new("RGB", (MAX_W, (ROW_H + 10) * len(rows) + 10), "white")
    d = ImageDraw.Draw(sheet)
    for k, r in enumerate(rows):
        y = 10 + k * (ROW_H + 10)
        d.text((8, y + 8), str(k + 1), fill="red", font=font)
        sheet.paste(r, (80, y))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()


class LlmCellFixer:
    def __init__(self, reader: TableReader, below: float = 0.6, batch: int = 40):
        self.reader, self.below, self.batch = reader, below, batch

    def pick(self, grid: List[List[str]], conf: List[List[float]], flagged: Set[Pos]) -> List[Pos]:
        """Cells with text that the recognizer was unsure of, or that a rule flagged."""
        return [(r, c) for r, row in enumerate(grid) for c, t in enumerate(row)
                if t.strip() and (conf[r][c] < self.below or (r, c) in flagged)]

    def fix(self, grid: List[List[str]], pieces: Dict[Pos, Image.Image], cells: Sequence[Pos]) -> Dict[Pos, str]:
        """{(row, col): new text} for the cells the model read back; a batch that fails is skipped, never guessed."""
        out: Dict[Pos, str] = {}
        cells = [p for p in cells if p in pieces]
        for i in range(0, len(cells), self.batch):
            part = cells[i:i + self.batch]
            try:
                ans = self.reader.ask_json(contact_sheet([pieces[p] for p in part]), load_prompt("cell_reread"), "cell_reread")
            except Exception:  # noqa: BLE001 - the recognizer's reading stays when the model cannot help
                continue
            if not isinstance(ans, dict):
                continue
            for k, pos in enumerate(part, 1):
                text = ans.get(str(k))
                if isinstance(text, str) and text.strip():
                    out[pos] = text.strip()
        return out
