import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateOcrJob, useDrawingTypes, useUpload } from '../../api/hooks';
import { useToast } from '../../components/ui/feedback';
import { Icon } from '../../components/ui/Icon';
import { Button, IconButton, Spinner } from '../../components/ui/primitives';
import { cx } from '../../lib/cx';
import { fmtSize } from '../../lib/format';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export const MAX_PAGES = 20;
export type Mode = 'steel' | 'ocr';
const TITLE: Record<Mode, string> = { steel: 'Phân tích bản vẽ', ocr: 'Trích xuất bảng' };

const LABEL = 'text-2xs font-medium uppercase tracking-wider text-mute';
const FIELD = 'h-8 min-w-0 rounded-md border border-strong bg-white px-2 hover:border-mute focus:border-primary focus:outline-none focus:shadow-ring';

/** Page numbers -> "1,3-5". */
export const toSpec = (pages: number[]) => {
  const out: string[] = [];
  for (let i = 0; i < pages.length; i++) {
    let j = i;
    while (j + 1 < pages.length && pages[j + 1] === pages[j] + 1) j++;
    out.push(j > i ? `${pages[i]}-${pages[j]}` : `${pages[i]}`);
    i = j;
  }
  return out.join(',');
};

/** One page of the open PDF drawn to a JPEG whose longer side is `side` px. */
async function drawPage(doc: pdfjs.PDFDocumentProxy, n: number, side: number, quality: number): Promise<string> {
  const page = await doc.getPage(n);
  const [, , w, h] = page.view;
  const vp = page.getViewport({ scale: side / Math.max(w, h) });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(vp.width);
  canvas.height = Math.ceil(vp.height);
  await page.render({ canvasContext: canvas.getContext('2d')!, viewport: vp }).promise;
  return canvas.toDataURL('image/jpeg', quality);
}

/**
 * The popup after a PDF is chosen on either tool's page: that tool's options, then start. Nothing is uploaded before the button.
 * Trích xuất bảng shows every page as a thumbnail to tick (a magnifier opens a large view to tell which pages hold tables).
 */
export function UploadDialog({ mode, file, onClose }: { mode: Mode; file: File | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  const navigate = useNavigate();
  const toast = useToast();
  const upload = useUpload();
  const ocr = useCreateOcrJob();
  const types = useDrawingTypes().data ?? [];

  const [total, setTotal] = useState(0);
  const [thumbs, setThumbs] = useState<(string | null)[]>([]);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [big, setBig] = useState<{ page: number; url: string | null } | null>(null);
  const [drawingType, setDrawingType] = useState('');
  const [rotate, setRotate] = useState('auto');
  const busy = upload.isPending || ocr.isPending;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (file && !el.open) el.showModal();
    if (!file && el.open) el.close();
  }, [file]);

  // Steel drawings are read as a whole and were always upright; scans for extraction are more often turned.
  useEffect(() => { setRotate(mode === 'ocr' ? 'auto' : '0'); setChosen(new Set()); setBig(null); }, [file, mode]);

  // Open the PDF in the browser; for the extraction tool draw a small picture of every page, one after another.
  useEffect(() => {
    setTotal(0); setThumbs([]);
    docRef.current = null;
    if (!file) return;
    let cancelled = false;
    (async () => {
      try {
        const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
        if (cancelled) { void doc.destroy(); return; }
        docRef.current = doc;
        setTotal(doc.numPages);
        if (mode !== 'ocr') return;
        setThumbs(Array(doc.numPages).fill(null));
        for (let n = 1; n <= doc.numPages && !cancelled; n++) {
          const url = await drawPage(doc, n, 260, 0.7);
          if (!cancelled) setThumbs((t) => t.map((x, i) => (i === n - 1 ? url : x)));
        }
      } catch {
        if (!cancelled) toast('Không đọc được file PDF này', { kind: 'error' });
      }
    })();
    return () => { cancelled = true; void docRef.current?.destroy(); docRef.current = null; };
  }, [file, mode, toast]);

  const toggle = (n: number) => setChosen((c) => {
    const s = new Set(c);
    if (!s.delete(n)) s.add(n);
    return s;
  });
  const pages = [...chosen].sort((a, b) => a - b);
  const tooMany = pages.length > MAX_PAGES;

  const openBig = async (n: number) => {
    setBig({ page: n, url: null });
    try {
      const doc = docRef.current;
      if (doc) { const url = await drawPage(doc, n, 1400, 0.85); setBig((b) => (b && b.page === n ? { page: n, url } : b)); }
    } catch {
      setBig(null);
    }
  };

  const start = async () => {
    if (!file) return;
    try {
      if (mode === 'ocr') {
        if (!pages.length || tooMany) return;
        const { id } = await ocr.mutateAsync({ file, pages: toSpec(pages), rotate });
        navigate(`/extract/job/${id}`);
      } else {
        const { id } = await upload.mutateAsync({ file, options: { rotate: Number(rotate) as 0 | 90 | 180 | 270, cols: 1, rows: 1, drawingType: drawingType || undefined } });
        toast('Đã nhận bản vẽ, bắt đầu phân tích', { kind: 'success' });
        navigate(`/job/${id}`);
      }
      onClose();
    } catch (e) {
      toast((e as Error).message, { kind: 'error' });
    }
  };

  const rotations = mode === 'ocr' ? ['auto', '0', '90', '180', '270'] : ['0', '90', '180', '270'];

  return (
    <dialog ref={ref} aria-label={TITLE[mode]} onClose={onClose} onClick={(e) => { if (e.target === ref.current && !busy) onClose(); }}
      className={cx('rounded-lg border border-strong bg-white p-0 text-ink shadow-modal', mode === 'ocr' ? 'w-[min(920px,calc(100vw-32px))]' : 'w-[min(520px,calc(100vw-32px))]')}>
      {file && (
        <div className="relative flex max-h-[calc(100dvh-48px)] flex-col">
          <div className="flex items-center gap-2.5 border-b border-strong bg-chrome px-4 py-2.5">
            <Icon name="file" size={20} />
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{file.name}</div>
              <div className="text-2xs text-mute">{TITLE[mode]} · {fmtSize(file.size)}{total ? ` · ${total} trang` : ''}</div>
            </div>
            <Button size="sm" variant="ghost" disabled={busy} onClick={onClose}>Hủy</Button>
          </div>

          {mode === 'ocr' && (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
                <span className="text-xs text-mute">Bấm vào các trang có bảng để chọn (tối đa {MAX_PAGES} trang). Bấm kính lúp để xem trang lớn hơn.</span>
                <span className="flex-1" />
                <span className={cx('text-xs font-medium', tooMany ? 'text-danger' : 'text-ink-2')}>Đã chọn {pages.length}</span>
                <Button size="sm" disabled={!total} onClick={() => setChosen(new Set(Array.from({ length: Math.min(total, MAX_PAGES) }, (_, i) => i + 1)))}>
                  {total > MAX_PAGES ? `${MAX_PAGES} trang đầu` : 'Chọn tất cả'}
                </Button>
                <Button size="sm" variant="ghost" disabled={!pages.length} onClick={() => setChosen(new Set())}>Bỏ chọn</Button>
              </div>
              <div className="min-h-[220px] flex-1 overflow-auto bg-surface p-3.5">
                <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2.5">
                  {thumbs.map((src, i) => {
                    const n = i + 1;
                    const on = chosen.has(n);
                    return (
                      <div key={n} className="relative">
                        <button type="button" aria-pressed={on} aria-label={`Trang ${n}`} onClick={() => toggle(n)}
                          className={cx('flex w-full flex-col items-center gap-1 border p-1.5 text-xs transition-colors',
                            on ? 'border-primary bg-primary-soft' : 'border-line bg-white hover:border-mute')}>
                          <div className="grid h-[130px] w-full place-items-center overflow-hidden bg-surface">
                            {src ? <img src={src} alt="" className="max-h-full max-w-full object-contain" /> : <Spinner />}
                          </div>
                          <span className="font-medium">Trang {n}</span>
                        </button>
                        {on && <span aria-hidden="true" className="pointer-events-none absolute right-1.5 top-1.5 grid size-5 place-items-center rounded-full bg-primary text-white"><Icon name="check" size={14} /></span>}
                        <IconButton icon="zoomin" label={`Xem lớn trang ${n}`} className="absolute bottom-7 right-1.5 bg-white/90" onClick={() => void openBig(n)} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {mode === 'steel' && types.length > 1 && (
            <div className="flex flex-col gap-1 border-b border-line px-4 py-3">
              <label htmlFor="u-type" className={LABEL}>Loại bản vẽ</label>
              <select id="u-type" className={FIELD} value={drawingType || types.find((t) => t.default)?.key || ''} onChange={(e) => setDrawingType(e.target.value)}>
                {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-white px-4 py-2.5">
            <div className="flex items-center gap-2">
              <label htmlFor="u-rot" className={LABEL}>{mode === 'ocr' ? 'Xoay bản scan' : 'Xoay trang'}</label>
              <select id="u-rot" className={FIELD} value={rotate} onChange={(e) => setRotate(e.target.value)}>
                {rotations.map((v) => <option key={v} value={v}>{v === 'auto' ? 'Tự động' : `${v}°`}</option>)}
              </select>
            </div>
            <Button variant="primary" icon={mode === 'ocr' ? 'download' : 'upload'} loading={busy} disabled={mode === 'ocr' && (!pages.length || tooMany)} onClick={start}>
              {busy ? 'Đang gửi…' : mode === 'ocr' ? `Trích xuất${pages.length && !tooMany ? ` ${pages.length} trang` : ''}` : 'Bắt đầu phân tích'}
            </Button>
          </div>

          {big && (
            <div role="dialog" aria-label={`Trang ${big.page}`} className="absolute inset-0 z-10 flex flex-col bg-ink/80">
              <div className="flex items-center justify-between gap-3 px-4 py-2 text-white">
                <strong>Trang {big.page}</strong>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={() => toggle(big.page)}>{chosen.has(big.page) ? 'Bỏ chọn trang này' : 'Chọn trang này'}</Button>
                  <Button size="sm" variant="ghost" className="text-white" onClick={() => setBig(null)}>Đóng</Button>
                </div>
              </div>
              <div className="grid min-h-0 flex-1 place-items-center overflow-auto p-3" onClick={() => setBig(null)}>
                {big.url ? <img src={big.url} alt={`Trang ${big.page}`} className="max-h-full max-w-full bg-white object-contain" /> : <Spinner className="size-6" />}
              </div>
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}
