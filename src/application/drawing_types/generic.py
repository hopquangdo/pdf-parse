"""Fallback: cut every page into regions and let one reader transcribe whatever schedule rows it sees."""
from src.application.drawing_types.base import ExtractionContext, ExtractionOutcome
from src.domain.models import Issue


class GenericRegions:
    key = "generic"
    label = "Any drawing (read page regions)"

    def extract(self, ctx: ExtractionContext) -> ExtractionOutcome:
        o = ctx.options
        rotate, cols, rows = o.get("rotate", 0), o.get("cols", 1), o.get("rows", 1)
        with ctx.step("render_regions", rotate=rotate, cols=cols, rows=rows) as d:
            tiles = [t for page in ctx.pages for t in ctx.renderer.render_tiles(ctx.pdf, page, rotate=rotate, cols=cols, rows=rows)]
            d["regions"] = len(tiles)
        with ctx.step("read_regions", workers=ctx.workers) as d:
            results = ctx.run_parallel(lambda t: ctx.read_region(t[1], t[0]), tiles)
            d["regions"] = len(tiles)
            d["failed_regions"] = sum(1 for _, err in results if err is not None)
        out = ExtractionOutcome()
        for (label, _), (res, err) in zip(tiles, results):
            raws, rerr = res if res is not None else ([], err)
            rerr = rerr or err
            if rerr is not None:
                out.issues.append(Issue("error", f"{label}: không đọc được ({type(rerr).__name__}: {str(rerr)[:120]})"))
            out.rows.extend(raws)
        return out
