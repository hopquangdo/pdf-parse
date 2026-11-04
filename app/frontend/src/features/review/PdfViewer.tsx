import * as pdfjs from 'pdfjs-dist';
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { api } from '../../api/client';
import { Icon } from '../../components/ui/Icon';
import { Button, IconButton, Spinner } from '../../components/ui/primitives';
import { cx } from '../../lib/cx';
import { useStored } from '../../lib/storage';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const MIN_K = 0.02; // screen px per PDF point
const MAX_K = 30;
const GAP = 28; // world units between pages
const MAX_COLS = 5; // most pages side by side before the grid wraps
const MARGIN = 24; // screen px kept around the content when fitting
const MAX_BITMAP_SIDE = 4096;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

interface View { x: number; y: number; k: number } // world → screen: p·k + (x, y)
interface PageBox { n: number; x: number; y: number; w: number; h: number; rotation: number }

/**
 * Infinite canvas holding every page of the PDF: wheel zooms around the pointer, drag pans, pinch zooms on touch.
 * Pages are positioned in world units; the whole world moves with one CSS transform, and pdf.js re-renders the
 * visible pages at the settled zoom so they stay sharp.
 */
export function PdfViewer({ jobId, className, fitKey }: { jobId: string; className?: string; fitKey?: string }) {
  const storageKey = jobId;
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PDFPageProxy[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [rotations, setRotations] = useStored<Record<number, number>>(`pdf-rot:${storageKey}`, {});
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const [settledK, setSettledK] = useState(1);
  const [stageSize, setStageSize] = useState({ w: 0, h: 0 });
  const [pageDraft, setPageDraft] = useState('1');
  const [grabbing, setGrabbing] = useState(false);

  const stage = useRef<HTMLDivElement>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const baseK = useRef(1); // zoom that fits page 1 to the width: the "100%" reference
  const fitted = useRef(false);
  const refit = useRef(false); // set when the pane was resized by a layout change: fit again once the new size is measured
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const pinch = useRef<{ dist: number; k: number } | null>(null);

  /* ---- load the document and every page's geometry ---- */
  useEffect(() => {
    setDoc(null); setPages([]); setError(null); fitted.current = false;
    let cancelled = false;
    let task: ReturnType<typeof pdfjs.getDocument> | null = null;
    // pdf.js cannot send an Authorization header, so the bytes come through the authenticated client instead.
    api.fetchPdf(jobId)
      .then((data) => {
        if (cancelled) return undefined;
        task = pdfjs.getDocument({ data });
        return task.promise;
      })
      .then(async (d) => {
        if (!d || cancelled) return;
        const all = await Promise.all(Array.from({ length: d.numPages }, (_, i) => d.getPage(i + 1)));
        if (!cancelled) { setDoc(d); setPages(all); }
      })
      .catch((e: Error) => { if (!cancelled) setError(e.message || 'Không mở được file PDF'); });
    return () => { cancelled = true; if (task) void task.destroy(); };
  }, [jobId, attempt]);

  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setStageSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setStageSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  /* ---- layout: pages flow into a balanced grid (2 -> 2 across, 3 -> 3, ... up to MAX_COLS, then wrap evenly);
     portrait sheets default to 90° (they hold landscape drawings) ---- */
  const layout = useMemo(() => {
    const sizes = pages.map((p, i) => {
      const natural = p.getViewport({ scale: 1 });
      // pdf.js turns pages clockwise; these portrait sheets hold landscape drawings that read upright after 270° (= 90° anticlockwise).
      const user = rotations[i + 1] ?? (natural.width < natural.height ? 270 : 0);
      const rotation = (p.rotate + user) % 360;
      const vp = p.getViewport({ scale: 1, rotation });
      return { w: vp.width, h: vp.height, rotation };
    });
    const count = sizes.length;
    const cols = count ? Math.ceil(count / Math.ceil(count / MAX_COLS)) : 1;
    const rows = count ? Math.ceil(count / cols) : 0;
    const colW = Array<number>(cols).fill(0);
    const rowH = Array<number>(rows).fill(0);
    sizes.forEach((s, i) => {
      colW[i % cols] = Math.max(colW[i % cols], s.w);
      rowH[Math.floor(i / cols)] = Math.max(rowH[Math.floor(i / cols)], s.h);
    });
    const colX = colW.map((_, c) => colW.slice(0, c).reduce((t, w) => t + w + GAP, 0));
    const rowY = rowH.map((_, r) => rowH.slice(0, r).reduce((t, h) => t + h + GAP, 0));
    const boxes: PageBox[] = sizes.map((s, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      return { n: i + 1, x: colX[c] + (colW[c] - s.w) / 2, y: rowY[r] + (rowH[r] - s.h) / 2, w: s.w, h: s.h, rotation: s.rotation };
    });
    const sum = (a: number[]) => a.reduce((t, v) => t + v, 0);
    return { boxes, cols, w: sum(colW) + Math.max(0, cols - 1) * GAP, h: sum(rowH) + Math.max(0, rows - 1) * GAP };
  }, [pages, rotations]);

  /* ---- view helpers ---- */
  const fitWidth = useCallback((pageIdx: number) => {
    const b = layout.boxes[pageIdx];
    if (!b || !stageSize.w) return;
    const k = clamp((stageSize.w - MARGIN * 2) / b.w, MIN_K, MAX_K);
    setView({ k, x: (stageSize.w - b.w * k) / 2 - b.x * k, y: MARGIN - b.y * k });
    return k;
  }, [layout, stageSize]);

  const fitAll = useCallback(() => {
    if (!layout.w || !stageSize.w) return;
    const k = clamp(Math.min((stageSize.w - MARGIN * 2) / layout.w, (stageSize.h - MARGIN * 2) / layout.h), MIN_K, MAX_K);
    setView({ k, x: (stageSize.w - layout.w * k) / 2, y: (stageSize.h - layout.h * k) / 2 });
  }, [layout, stageSize]);

  useEffect(() => {
    if (fitted.current || !layout.boxes.length || !stageSize.w) return;
    fitted.current = true;
    if (layout.cols > 1) { fitAll(); return; }
    const k = fitWidth(0);
    if (k) baseK.current = k;
  }, [layout, stageSize, fitWidth, fitAll]);

  useEffect(() => {
    if (fitKey === undefined) return;
    refit.current = true;
    const t = setTimeout(() => { refit.current = false; }, 600);
    return () => clearTimeout(t);
  }, [fitKey]);
  useEffect(() => {
    if (!refit.current || !layout.boxes.length || !stageSize.w) return;
    refit.current = false;
    if (layout.cols > 1) fitAll(); else fitWidth(0);
  }, [stageSize, layout, fitAll, fitWidth]);

  const zoomAt = useCallback((factor: number, cx: number, cy: number) => {
    setView((v) => {
      const k = clamp(v.k * factor, MIN_K, MAX_K);
      const r = k / v.k;
      return { k, x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r };
    });
  }, []);
  const zoomCentre = (factor: number) => zoomAt(factor, stageSize.w / 2, stageSize.h / 2);

  useEffect(() => {
    const t = setTimeout(() => setSettledK(view.k), 140); // re-render at the new resolution once the gesture settles
    return () => clearTimeout(t);
  }, [view.k]);

  /* ---- current page and visible set ---- */
  const current = useMemo(() => {
    if (!layout.boxes.length) return 1;
    const wx = (stageSize.w / 2 - view.x) / view.k;
    const wy = (stageSize.h / 2 - view.y) / view.k;
    let best = 0, bestDist = Infinity;
    layout.boxes.forEach((b, i) => {
      const dx = wx < b.x ? b.x - wx : wx > b.x + b.w ? wx - (b.x + b.w) : 0;
      const dy = wy < b.y ? b.y - wy : wy > b.y + b.h ? wy - (b.y + b.h) : 0;
      const d = Math.hypot(dx, dy);
      if (d < bestDist) { best = i; bestDist = d; }
    });
    return best + 1;
  }, [layout, view, stageSize.w, stageSize.h]);
  useEffect(() => setPageDraft(String(current)), [current]);

  const visible = useMemo(() => {
    const padX = stageSize.w * 0.25, padY = stageSize.h * 0.25;
    return new Set(layout.boxes.filter((b) => {
      const sx = b.x * view.k + view.x, sy = b.y * view.k + view.y;
      return sx < stageSize.w + padX && sx + b.w * view.k > -padX && sy < stageSize.h + padY && sy + b.h * view.k > -padY;
    }).map((b) => b.n));
  }, [layout, view, stageSize]);

  const goto = (n: number) => { if (pages.length) { fitWidth(clamp(n, 1, pages.length) - 1); } };
  const rotateCurrent = () => {
    const box = layout.boxes[current - 1];
    if (!box) return;
    const p = pages[current - 1];
    const user = ((box.rotation - p.rotate) % 360 + 360) % 360;
    setRotations({ ...rotations, [current]: (user + 90) % 360 });
  };

  /* ---- input: wheel zoom (non-passive so the page does not scroll), drag pan, pinch ---- */
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      zoomAt(Math.exp(-e.deltaY * unit * (e.ctrlKey ? 0.01 : 0.0018)), e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    stage.current?.setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1) {
      gesture.current = { x: e.clientX, y: e.clientY, vx: viewRef.current.x, vy: viewRef.current.y };
      setGrabbing(true);
    } else if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y), k: viewRef.current.k };
      gesture.current = null;
    }
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2 && pinch.current && stage.current) {
      const [a, b] = [...pointers.current.values()];
      const rect = stage.current.getBoundingClientRect();
      const target = clamp(pinch.current.k * (Math.hypot(a.x - b.x, a.y - b.y) / pinch.current.dist), MIN_K, MAX_K);
      zoomAt(target / viewRef.current.k, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
    } else if (gesture.current) {
      const g = gesture.current;
      setView((v) => ({ ...v, x: g.vx + e.clientX - g.x, y: g.vy + e.clientY - g.y }));
    }
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(e.pointerId);
    pinch.current = null;
    if (pointers.current.size === 0) { gesture.current = null; setGrabbing(false); }
    else if (pointers.current.size === 1) {
      const [p] = [...pointers.current.values()];
      gesture.current = { x: p.x, y: p.y, vx: viewRef.current.x, vy: viewRef.current.y };
    }
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = 90;
    if (e.key === '+' || e.key === '=') zoomCentre(1.25);
    else if (e.key === '-') zoomCentre(1 / 1.25);
    else if (e.key === '0') goto(current);
    else if (e.key === '9') fitAll();
    else if (e.key === 'PageDown') goto(current + 1);
    else if (e.key === 'PageUp') goto(current - 1);
    else if (e.key === 'ArrowLeft') setView((v) => ({ ...v, x: v.x + step }));
    else if (e.key === 'ArrowRight') setView((v) => ({ ...v, x: v.x - step }));
    else if (e.key === 'ArrowUp') setView((v) => ({ ...v, y: v.y + step }));
    else if (e.key === 'ArrowDown') setView((v) => ({ ...v, y: v.y - step }));
    else return;
    e.preventDefault();
  };

  const percent = Math.round((view.k / baseK.current) * 100);
  const loading = !doc && !error;
  const group = 'flex items-center gap-1';
  const lbl = 'lbl min-w-12 text-center font-mono text-2xs tabular-nums text-mute';

  return (
    <div className={cx('viewer flex min-h-0 min-w-0 flex-col bg-surface2', className)}>
      <div role="toolbar" aria-label="Trình xem bản vẽ" className="viewer-bar flex flex-wrap items-center gap-1.5 border-b border-strong bg-chrome px-2.5 py-1.5">
        <div className={group}>
          <IconButton icon="chevronLeft" label="Trang trước" disabled={current <= 1} onClick={() => goto(current - 1)} />
          <input aria-label="Số trang" inputMode="numeric" value={pageDraft}
            onChange={(e) => setPageDraft(e.target.value.replace(/\D/g, ''))}
            onBlur={() => goto(Number(pageDraft) || current)} onKeyDown={(e) => { if (e.key === 'Enter') goto(Number(pageDraft) || current); }}
            className="h-[26px] w-[52px] rounded border border-strong bg-white px-1 text-center font-mono tabular-nums focus:border-primary focus:outline-none focus:shadow-ring" />
          <span className={lbl}>/ {pages.length || '–'}</span>
          <IconButton icon="chevronRight" label="Trang sau" disabled={!pages.length || current >= pages.length} onClick={() => goto(current + 1)} />
        </div>
        <span className="flex-1" />
        <div className={group}>
          <IconButton icon="rotate" label="Xoay trang này 90°" onClick={rotateCurrent} />
          <IconButton icon="zoomout" label="Thu nhỏ" onClick={() => zoomCentre(1 / 1.25)} />
          <span className={lbl} aria-live="polite">{percent}%</span>
          <IconButton icon="zoomin" label="Phóng to" onClick={() => zoomCentre(1.25)} />
          <IconButton icon="fit" label="Vừa chiều rộng trang (0)" onClick={() => goto(current)} />
          <IconButton icon="grid" label="Vừa tất cả trang (9)" onClick={fitAll} />
        </div>
      </div>
      <div ref={stage} tabIndex={0} role="application"
        aria-label="Khung bản vẽ: cuộn để phóng to, kéo để di chuyển, phím + và - để thu phóng, 0 vừa trang, 9 vừa tất cả trang"
        className={cx('viewer-stage relative min-h-0 flex-1 overflow-hidden', grabbing && 'grabbing')}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        onDoubleClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); zoomAt(e.shiftKey ? 0.5 : 2, e.clientX - r.left, e.clientY - r.top); }}
        onKeyDown={onKeyDown}>
        <div className="world" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})` }}>
          {doc && layout.boxes.map((b) => (
            <PageSurface key={b.n} page={pages[b.n - 1]} box={b} visible={visible.has(b.n)} zoom={settledK} baseK={baseK.current} />
          ))}
        </div>
        {(loading || error) && (
          <div className="viewer-overlay pointer-events-none absolute inset-0 grid place-items-center">
            <div className="pointer-events-auto flex items-center gap-2.5 border border-strong bg-white px-4 py-2.5 shadow-pop">
              {error ? (<><Icon name="alert" /><span>{error}</span><Button size="sm" onClick={() => setAttempt((a) => a + 1)}>Thử lại</Button></>)
                : (<><Spinner /><span className="text-mute">Đang tải bản vẽ…</span></>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** One page: a canvas sized in world units, with its bitmap re-rendered when the settled zoom outgrows it. */
const PageSurface = memo(function PageSurface({ page, box, visible, zoom, baseK }: {
  page: PDFPageProxy; box: PageBox; visible: boolean; zoom: number; baseK: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const rendered = useRef({ scale: 0, rotation: -1 });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  useEffect(() => {
    // Visible pages follow the zoom; hidden ones keep a cheap low-resolution bitmap so zooming out stays complete.
    const wanted = (visible ? zoom : Math.min(zoom, baseK * 0.6)) * dpr;
    const scale = Math.min(wanted, MAX_BITMAP_SIDE / Math.max(box.w, box.h));
    const done = rendered.current;
    if (done.rotation === box.rotation && done.scale >= scale * 0.9 && (visible || done.scale > 0)) {
      if (!visible || done.scale <= scale * 4) return; // already sharp enough (and not wastefully large)
    }
    let cancelled = false;
    let task: RenderTask | null = null;
    (async () => {
      try {
        const viewport = page.getViewport({ scale, rotation: box.rotation });
        const off = document.createElement('canvas');
        off.width = Math.max(1, Math.floor(viewport.width));
        off.height = Math.max(1, Math.floor(viewport.height));
        task = page.render({ canvasContext: off.getContext('2d')!, viewport });
        await task.promise;
        const el = canvas.current;
        if (cancelled || !el) return;
        el.width = off.width;
        el.height = off.height;
        el.getContext('2d')!.drawImage(off, 0, 0);
        rendered.current = { scale, rotation: box.rotation };
      } catch (e) {
        if ((e as Error).name !== 'RenderingCancelledException') console.warn('page render failed', e);
      }
    })();
    return () => { cancelled = true; task?.cancel(); };
  }, [page, box.rotation, box.w, box.h, visible, zoom, baseK, dpr]);

  return <canvas ref={canvas} className="page-canvas" data-page={box.n} aria-label={`Page ${box.n}`}
    style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />;
});
