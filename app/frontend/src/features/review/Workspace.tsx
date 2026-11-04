import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import type { DataGridHandle } from 'react-data-grid';
import { useBlocker } from 'react-router-dom';
import { api } from '../../api/client';
import { useExport, useSaveRows } from '../../api/hooks';
import type { ExportResult, Job, Row } from '../../api/types';
import { Crumbs, TopbarActions } from '../../components/shell/Shell';
import { ConfirmDialog, Dialog, useToast } from '../../components/ui/feedback';
import { Badge, Button, Segmented } from '../../components/ui/primitives';
import { cx } from '../../lib/cx';
import { abbr } from '../../lib/format';
import { compute, sumTotals, type Catalog } from '../../lib/formulas';
import { useStored } from '../../lib/storage';
import { invalidFields, isFlagged, issuesByMark, newId, sameRow, toApiRows, toSheetRows, type SheetRow } from '../../lib/sheet';
import { IssuesPanel } from './IssuesPanel';
import { PdfViewer } from './PdfViewer';
import { SheetGrid } from './SheetGrid';
import { Splitter } from './Splitter';

type Filter = 'all' | 'flag' | 'edited';
type Pane = 'drawing' | 'data';
const FIRST_EDITABLE_COL = 2; // rn, select, then Section

export function Workspace({ job, catalog: baseCatalog }: { job: Job; catalog: Catalog }) {
  const toast = useToast();
  const saveMutation = useSaveRows(job.id);
  const exportMutation = useExport();
  const grid = useRef<DataGridHandle>(null);
  const split = useRef<HTMLDivElement>(null);

  const initial = useMemo(() => {
    const rows = toSheetRows(job.rows);
    return { rows, baseline: new Map(rows.map((r) => [r.id, { ...r } as Row])) };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed once; later server data is applied by save()
  }, []);
  const [rows, setRows] = useState<SheetRow[]>(initial.rows);
  const [baseline, setBaseline] = useState<Map<string, Row>>(initial.baseline);
  const [serverIssues, setServerIssues] = useState(job.issues);
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [flashId, setFlashId] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const [pane, setPane] = useState<Pane>('data');
  const [layout, setLayout] = useStored<'split' | 'table' | 'drawing'>('review-layout', 'split');
  // Hệ số sơn (template cell P3): scales every paint-area figure; saved per drawing and written into the export.
  const [paintFactor, setPaintFactor] = useStored<number>(`paint-factor:${job.id}`, baseCatalog.paint_factor);
  const [paintDraft, setPaintDraft] = useState(String(paintFactor));
  const catalog = useMemo<Catalog>(() => ({ ...baseCatalog, paint_factor: paintFactor }), [baseCatalog, paintFactor]);
  const [showInputs, setShowInputs] = useStored('review-show-inputs', false);
  const [leftPx, setLeftPx] = useStored<number | null>('review-left', null);
  const [confirmExport, setConfirmExport] = useState<{ rows: Row[]; warnings: number } | null>(null);
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [downloading, setDownloading] = useState(false);

  const byMark = useMemo(() => issuesByMark(serverIssues), [serverIssues]);
  // The template's formulas (Spec, J-N) evaluated live, so edits show their effect on mass immediately.
  const calc = useMemo(() => new Map(rows.map((r) => [r.id, compute(r, catalog)])), [rows, catalog]);
  const totals = useMemo(() => sumTotals(calc.values()), [calc]);
  const flagged = useCallback((r: SheetRow) => isFlagged(r, byMark) || !!calc.get(r.id)?.error, [byMark, calc]);
  const rowNumbers = useMemo(() => new Map(rows.map((r, i) => [r.id, i + 1])), [rows]);
  const isEdited = useCallback((r: SheetRow) => !sameRow(r, baseline.get(r.id)), [baseline]);
  const flaggedCount = rows.filter(flagged).length;
  const editedCount = rows.filter(isEdited).length;
  const dirty = rows.length !== baseline.size || editedCount > 0;
  const shown = useMemo(
    () => rows.filter((r) => filter === 'all' || (filter === 'flag' ? flagged(r) : isEdited(r))),
    [rows, filter, flagged, isEdited],
  );

  /* ---- navigation guards ---- */
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  /* ---- editing ---- */
  const commit = (updated: SheetRow[]) => {
    const byId = new Map(updated.map((r) => [r.id, r]));
    setRows((cur) => cur.map((r) => byId.get(r.id) ?? r));
  };

  const selectCell = (rowIdx: number, idx = FIRST_EDITABLE_COL, edit = false) => {
    setTimeout(() => {
      grid.current?.scrollToCell({ rowIdx, idx });
      grid.current?.selectCell({ rowIdx, idx }, edit);
    }, 0);
  };

  const addRow = () => {
    const last = rows[rows.length - 1];
    const fresh: SheetRow = { id: newId(), section: last?.section ?? '', mark: '', type: last?.type ?? 'L', w: '', t: null, len: '', qty: 1 };
    if (filter === 'edited' || filter === 'flag') setFilter('all');
    setRows([...rows, fresh]);
    selectCell(rows.length, FIRST_EDITABLE_COL + 1, true);
  };

  const deleteSelected = () => {
    const removed = rows.map((row, index) => ({ row, index })).filter((x) => selected.has(x.row.id));
    if (!removed.length) return;
    setRows(rows.filter((r) => !selected.has(r.id)));
    setSelected(new Set());
    toast(`Đã xóa ${removed.length} dòng`, {
      duration: 8000,
      action: {
        label: 'Hoàn tác',
        onClick: () => setRows((cur) => {
          const next = [...cur];
          for (const { row, index } of removed) next.splice(Math.min(index, next.length), 0, row);
          return next;
        }),
      },
    });
  };

  const focusMark = (mark: string) => {
    setFilter('all');
    const idx = rows.findIndex((r) => r.mark === mark);
    if (idx < 0) return;
    selectCell(idx, FIRST_EDITABLE_COL + 1);
    setFlashId(rows[idx].id);
    setTimeout(() => setFlashId(null), 1500);
  };

  const nextIssue = () => {
    if (!shown.length) return;
    const order = [...shown.keys()];
    const start = order.filter((i) => i > active).concat(order.filter((i) => i <= active));
    const hit = start.find((i) => flagged(shown[i]));
    if (hit === undefined) return toast('Không còn dòng nào cần soát', { kind: 'success' });
    selectCell(hit);
  };

  /* ---- persistence ---- */
  const save = async (): Promise<Job | null> => {
    const bad = rows.findIndex((r) => invalidFields(r).size > 0);
    if (bad >= 0) {
      setFilter('all');
      selectCell(bad);
      toast(`Dòng ${bad + 1} có ô không hợp lệ. Hãy sửa các ô viền đỏ.`, { kind: 'error' });
      return null;
    }
    try {
      const saved = await saveMutation.mutateAsync(toApiRows(rows));
      const fresh = toSheetRows(saved.rows);
      setRows(fresh);
      setBaseline(new Map(fresh.map((r) => [r.id, { ...r } as Row])));
      setServerIssues(saved.issues);
      setSelected(new Set());
      toast('Đã lưu', { kind: 'success' });
      return saved;
    } catch (e) {
      toast((e as Error).message, { kind: 'error' });
      return null;
    }
  };

  const runExport = async (apiRows: Row[]) => {
    try {
      setExported(await exportMutation.mutateAsync({ rows: apiRows, paintFactor, jobId: job.id }));
    } catch (e) {
      toast((e as Error).message, { kind: 'error' });
    }
  };

  const startExport = async () => {
    let apiRows = toApiRows(rows);
    let issues = serverIssues;
    if (dirty) {
      const saved = await save();
      if (!saved) return;
      apiRows = saved.rows;
      issues = saved.issues;
    }
    const warnings = issues.filter((i) => i.level !== 'info').length;
    if (warnings > 0) setConfirmExport({ rows: apiRows, warnings });
    else void runExport(apiRows);
  };

  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void saveRef.current();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const style = leftPx != null ? ({ '--left': `${leftPx}px` } as CSSProperties) : undefined;
  const tableOnly = layout === 'table';
  const drawingOnly = layout === 'drawing';

  return (
    <>
      <Crumbs items={[{ label: 'Lịch sử', to: '/jobs' }, { label: job.filename }]} />
      <TopbarActions>
        {dirty && <span className="max-sm:hidden"><Badge tone="warn">Chưa lưu</Badge></span>}
        <Button icon="save" title="Lưu (Ctrl+S)" onClick={() => void save()} disabled={!dirty} loading={saveMutation.isPending}><span className="max-sm:hidden">Lưu</span></Button>
        <Button variant="primary" icon="download" onClick={() => void startExport()} loading={exportMutation.isPending}>Xuất<span className="max-sm:hidden"> Excel (.xlsm)</span></Button>
      </TopbarActions>

      <div ref={split} data-pane={pane} data-layout={layout} style={style}
        className={cx('review relative grid h-full min-h-0 bg-white max-md:grid-cols-1 max-md:grid-rows-[auto_minmax(0,1fr)]',
          tableOnly ? 'grid-cols-[1px_minmax(0,1fr)]' : drawingOnly ? 'grid-cols-[minmax(0,1fr)_1px]' : 'grid-cols-[var(--left,44%)_1px_minmax(0,1fr)]')}>
        <div className="pane-switch hidden border-b border-line bg-white px-2.5 py-2 max-md:block">
          <Segmented<Pane> label="Khung" value={pane} onChange={setPane}
            options={[{ value: 'drawing', label: 'Bản vẽ' }, { value: 'data', label: 'Dữ liệu' }]} />
        </div>
        <PdfViewer jobId={job.id} fitKey={layout} className={cx(tableOnly && 'hidden', pane === 'data' && 'max-md:hidden')} />
        <Splitter container={split} width={leftPx} onChange={setLeftPx} layout={layout} onLayout={setLayout} className="max-md:hidden" />

        <section aria-label="Dữ liệu đã bóc tách" className={cx('data flex min-h-0 min-w-0 flex-col bg-white', drawingOnly && 'hidden', pane === 'drawing' && 'max-md:hidden')}>
          <div className="data-bar flex flex-wrap items-center gap-2.5 border-b border-line bg-chrome px-2.5 py-2">
            <div className="summary flex items-center gap-4 text-xs text-mute">
              <span><b className="font-mono font-medium text-ink">{rows.length}</b> dòng</span>
              <span><b className={cx('font-mono font-medium', flaggedCount ? 'text-warn' : 'text-ink')}>{flaggedCount}</b> cần soát</span>
              <span><b className="font-mono font-medium text-ink">{editedCount}</b> đã sửa</span>
            </div>
            <label className="flex items-center gap-1.5 text-xs text-mute" title="Hệ số sơn: nhân với mọi diện tích sơn (ô P3 của file mẫu)">
              Hệ số sơn
              <input type="number" min={0} step={0.1} inputMode="decimal" aria-label="Hệ số sơn" value={paintDraft}
                aria-invalid={!(Number(paintDraft) >= 0 && paintDraft !== '')}
                onChange={(e) => {
                  setPaintDraft(e.target.value);
                  const n = Number(e.target.value);
                  if (e.target.value !== '' && Number.isFinite(n) && n >= 0) setPaintFactor(n);
                }}
                onBlur={() => setPaintDraft(String(paintFactor))}
                className="h-[26px] w-16 rounded border border-strong bg-white px-1.5 text-right font-mono tabular-nums text-ink focus:border-primary focus:outline-none focus:shadow-ring aria-[invalid=true]:border-danger" />
            </label>
            <span className="flex-1" />
            <Segmented<Filter> label="Lọc dòng" value={filter} onChange={setFilter} options={[
              { value: 'all', label: 'Tất cả' }, { value: 'flag', label: `Cần soát (${flaggedCount})` }, { value: 'edited', label: `Đã sửa (${editedCount})` },
            ]} />
          </div>
          <div className="data-bar flex flex-wrap items-center gap-2.5 border-b border-line bg-white px-2.5 py-2">
            <Button size="sm" icon="arrowDown" onClick={nextIssue} disabled={!flaggedCount}>Lỗi tiếp theo</Button>
            <Button size="sm" icon="plus" onClick={addRow}>Thêm dòng</Button>
            <Button size="sm" icon="trash" onClick={deleteSelected} disabled={!selected.size}>
              {selected.size ? `Xóa ${selected.size}` : 'Xóa'}
            </Button>
            <span className="flex-1" />
            <Button size="sm" icon="columns" aria-pressed={showInputs} onClick={() => setShowInputs(!showInputs)}>
              {showInputs ? 'Ẩn cột nhập' : 'Hiện cột nhập'}
            </Button>
          </div>
          <IssuesPanel issues={serverIssues} onSelect={focusMark} />
          <div className="flex min-h-0 flex-1">
            <SheetGrid ref={grid} rows={shown} rowNumbers={rowNumbers} byMark={byMark} baseline={baseline} calc={calc} totals={totals} showInputs={showInputs}
              isFlagged={flagged} selected={selected}
              flashId={flashId} onSelectedChange={setSelected} onCommit={commit} onActiveRow={setActive} />
          </div>
          {job.usage && job.usage.calls > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-1.5 border-t border-strong bg-chrome px-2.5 py-1.5">
              <span className="usage font-mono text-2xs tabular-nums text-mute" title="Mức dùng mô hình AI khi đọc bản vẽ này">
                AI · {job.usage.calls} lượt gọi · vào {abbr(job.usage.input_tokens)} · cache {abbr(job.usage.cached_tokens)} · ra {abbr(job.usage.output_tokens)}
                {' '}· ${job.usage.cost_usd.toFixed(4)} · {job.usage.cost_vnd.toLocaleString('vi-VN')}đ{job.usage.wall_seconds != null && ` · ${job.usage.wall_seconds.toFixed(1)}s`}
                {job.usage.unpriced_calls > 0 && ` (${job.usage.unpriced_calls} lượt chưa tính giá)`}
              </span>
              <button type="button" className="text-2xs text-primary hover:underline" title="Tải nhật ký đầy đủ của lượt chạy: các bước, từng lượt gọi mô hình và chi phí, kết quả"
                onClick={() => void api.downloadRunLog(job.id).catch((e: Error) => toast(e.message, { kind: 'error' }))}>Nhật ký chạy</button>
            </div>
          )}
        </section>
      </div>

      <ConfirmDialog open={blocker.state === 'blocked'} title="Bỏ các thay đổi chưa lưu?"
        message="Bạn có chỉnh sửa chưa lưu. Rời đi bây giờ sẽ mất các chỉnh sửa này."
        confirmLabel="Bỏ và rời đi" cancelLabel="Tiếp tục sửa" danger
        onConfirm={() => blocker.state === 'blocked' && blocker.proceed()} onCancel={() => blocker.state === 'blocked' && blocker.reset()} />

      <ConfirmDialog open={!!confirmExport} title="Còn cảnh báo chưa xử lý"
        message={`Bản vẽ này còn ${confirmExport?.warnings ?? 0} cảnh báo. Vẫn xuất Excel?`}
        confirmLabel="Vẫn xuất" cancelLabel="Quay lại"
        onConfirm={() => { const c = confirmExport; setConfirmExport(null); if (c) void runExport(c.rows); }}
        onCancel={() => setConfirmExport(null)} />

      <Dialog open={!!exported} title="File Excel đã sẵn sàng" onClose={() => setExported(null)}
        actions={<>
          <Button onClick={() => setExported(null)}>Đóng</Button>
          {exported && (
            <Button variant="primary" icon="download" loading={downloading}
              onClick={() => {
                setDownloading(true);
                api.downloadExport(exported.id, job.filename)
                  .then(() => setExported(null))
                  .catch((e: Error) => toast(e.message, { kind: 'error' }))
                  .finally(() => setDownloading(false));
              }}>
              Tải .xlsm
            </Button>
          )}
        </>}>
        {exported && (
          <>
            <dl className="m-0 grid grid-cols-[auto_1fr] border border-line text-sm">
              {[['Số dòng', exported.rows], ['Khối lượng dự kiến', `${exported.expected_mass_kg.toLocaleString('vi-VN')} kg`], ['Dòng chưa có khối lượng', exported.rows_without_mass]].map(([k, v]) => (
                <div key={k as string} className="contents">
                  <dt className="border-b border-line bg-surface px-2.5 py-1.5 text-2xs font-medium uppercase tracking-wider text-mute last-of-type:border-b-0">{k}</dt>
                  <dd className="m-0 border-b border-line px-2.5 py-1.5 text-right font-mono font-medium tabular-nums text-ink last-of-type:border-b-0">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2.5">Excel sẽ tính các công thức khi mở file. Bu lông và bản mã chưa có chi tiết cần được bổ sung trước khi dùng.</p>
          </>
        )}
      </Dialog>
    </>
  );
}
