import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../../api/client';
import { useOcrJob, useRetryOcrJob } from '../../api/hooks';
import type { OcrPage, OcrTable } from '../../api/types';
import { Page } from '../../components/layout/Page';
import { useToast } from '../../components/ui/feedback';
import { Button, EmptyState, Panel, Skeleton, Spinner } from '../../components/ui/primitives';
import { cx } from '../../lib/cx';

const CRUMB = { label: 'Lịch sử', to: '/jobs' };

/** Result screen of one OCR run: pages on the left, the table of the chosen page on the right, Excel download on top. */
export function OcrJobPage() {
  const { id = '' } = useParams();
  const toast = useToast();
  const { data: job, isLoading, error } = useOcrJob(id);
  const retry = useRetryOcrJob(id);
  const [picked, setPicked] = useState<number | null>(null);

  if (isLoading) {
    return <Page crumbs={[CRUMB, { label: '…' }]}><Panel className="grid gap-3 p-4"><Skeleton h={24} w="40%" /><Skeleton h={200} /></Panel></Page>;
  }
  if (error || !job) {
    return (
      <Page crumbs={[CRUMB, { label: 'Không tìm thấy' }]}>
        <Panel><EmptyState title="Không mở được lượt OCR này">{(error as Error | null)?.message ?? 'Lỗi không xác định'}</EmptyState></Panel>
      </Page>
    );
  }

  const running = job.status === 'pending' || job.status === 'running';
  const done = job.pages.filter((p) => p.status === 'done');
  const sheets = done.reduce((n, p) => n + p.tables.length, 0);
  const failed = job.pages.filter((p) => p.status === 'error');
  const cost = job.pages.reduce((a, p) => a + (p.cost_vnd || 0), 0);
  const active = job.pages.find((p) => p.page === picked) ?? done[0] ?? job.pages[0];
  const base = job.filename.replace(/\.[^.]+$/, '');

  const download = () => api.downloadOcrXlsx(job.id, `${base}.xlsx`).catch((e: Error) => toast(e.message, { kind: 'error' }));
  const retryFailed = () => retry.mutateAsync().catch((e: Error) => toast(e.message, { kind: 'error' }));

  return (
    <Page crumbs={[CRUMB, { label: job.filename }]} fill
      actions={<>
        {!running && failed.length > 0 && <Button size="sm" loading={retry.isPending} onClick={retryFailed}>Đọc lại {failed.length} trang lỗi</Button>}
        <Button variant="primary" size="sm" icon="download" disabled={!done.length} onClick={download}>
          Tải Excel{sheets ? ` (${sheets} sheet)` : ''}
        </Button>
      </>}>
      <div className="flex flex-none flex-wrap items-center gap-3 text-xs text-ink-2" role="status">
        {running ? <><Spinner /><span>Đang đọc, xong {done.length + failed.length}/{job.pages.length} trang. Bạn có thể rời trang này, kết quả vẫn được lưu.</span></>
          : <span className="font-medium text-ink">Đã đọc {done.length}/{job.pages.length} trang{failed.length ? `, ${failed.length} trang lỗi` : ''}</span>}
        {cost > 0 && <span className="text-mute">~{cost.toLocaleString('vi-VN')}đ</span>}
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[200px_minmax(0,1fr)]">
        <Panel title="Các trang" className="min-h-0 overflow-auto">
          <ul className="flex flex-col max-lg:flex-row max-lg:overflow-x-auto">
            {job.pages.map((p) => (
              <li key={p.page}>
                <button type="button" onClick={() => setPicked(p.page)}
                  className={cx('flex w-full items-center gap-2 border-l-[3px] px-3 py-2 text-left text-xs whitespace-nowrap',
                    active?.page === p.page ? 'border-l-primary bg-primary-soft text-primary' : 'border-l-transparent hover:bg-surface')}>
                  <span className="flex-1 font-medium">Trang {p.page}</span>
                  <PageStatus p={p} />
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={active ? `Trang ${active.page}` : 'Kết quả'} fill>
          <PageResult p={active} />
        </Panel>
      </div>
    </Page>
  );
}

function PageStatus({ p }: { p: OcrPage }) {
  if (p.status === 'run') return <Spinner />;
  if (p.status === 'wait') return <span className="text-mute">đang chờ</span>;
  if (p.status === 'done') return <span className="text-ok">{p.tables.length} bảng</span>;
  return <span className="text-danger">lỗi</span>;
}

function PageResult({ p }: { p?: OcrPage }) {
  if (!p) return <EmptyState title="Chưa có trang nào" />;
  if (p.status === 'error') return <p role="alert" className="p-4 text-xs text-danger">{p.error || 'Không đọc được trang này.'}</p>;
  if (p.status !== 'done') {
    return <div className="flex items-center gap-2 p-4 text-xs text-mute"><Spinner />{p.status === 'run' ? 'Đang đọc trang này, khoảng 30–60 giây…' : 'Đang chờ đến lượt…'}</div>;
  }
  return <TableTabs key={p.page} tables={p.tables} />;
}

/** Every table of one page: a tab per table (each becomes one Excel sheet) above the table itself. */
function TableTabs({ tables }: { tables: OcrTable[] }) {
  const [k, setK] = useState(0);
  const t = tables[Math.min(k, tables.length - 1)];
  if (!t) return <EmptyState title="Không tìm thấy bảng nào trên trang này" />;
  return (
    <div className="flex h-full min-h-0 flex-col">
      {tables.length > 1 && (
        <div role="tablist" className="flex flex-none gap-1 border-b border-line bg-surface px-2 pt-1.5">
          {tables.map((x, i) => (
            <button key={x.name} role="tab" aria-selected={i === k} type="button" onClick={() => setK(i)}
              className={cx('rounded-t border border-b-0 px-3 py-1.5 text-xs', i === k ? 'border-line bg-white font-medium text-primary' : 'border-transparent text-mute hover:text-ink')}>
              Bảng {i + 1} <span className="text-mute">({x.rows.length} dòng)</span>
            </button>
          ))}
        </div>
      )}
      {t.flags && Object.keys(t.flags).length > 0 && (
        <p className="border-b border-warn-line bg-warn-soft px-3 py-1.5 text-xs text-warn">{Object.keys(t.flags).length} ô tô vàng cần soát: di chuột vào ô để xem lý do.</p>
      )}
      {t.warnings.length > 0 && <p className="border-b border-warn-line bg-warn-soft px-3 py-1.5 text-xs text-warn">{t.warnings.join(' · ')}</p>}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={i} className={i === 0 ? 'sticky top-0 bg-primary-soft font-medium' : 'odd:bg-white even:bg-surface'}>
                {r.map((c, j) => {
                  const why = t.flags?.[`${i},${j}`];
                  return <td key={j} title={why} className={cx('border border-line px-2 py-1 align-top', why && 'bg-warn-soft')}>{c}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
