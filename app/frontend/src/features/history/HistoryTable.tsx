import { useNavigate } from 'react-router-dom';
import type { HistoryItem } from '../../api/types';
import { cx } from '../../lib/cx';
import { Icon } from '../../components/ui/Icon';
import { Badge, EmptyState, StatusBadge } from '../../components/ui/primitives';
import { fmtTime } from '../../lib/format';

export type SortKey = 'kind' | 'filename' | 'status' | 'page_count' | 'rows' | 'issues' | 'cost_vnd' | 'wall_seconds' | 'created_at';
export interface Sort { key: SortKey; dir: 'asc' | 'desc' }

export const KIND_LABEL: Record<HistoryItem['kind'], string> = { steel: 'Phân tích bản vẽ', ocr: 'Trích xuất bảng' };
/** Where a history line opens: each tool has its own result screen. */
export const openPath = (j: Pick<HistoryItem, 'kind' | 'id'>) => (j.kind === 'ocr' ? `/extract/job/${j.id}` : `/job/${j.id}`);

const COLUMNS: { key: SortKey; label: string; right?: boolean }[] = [
  { key: 'kind', label: 'Loại' },
  { key: 'filename', label: 'Tên file' },
  { key: 'status', label: 'Trạng thái' },
  { key: 'page_count', label: 'Trang', right: true },
  { key: 'rows', label: 'Dòng', right: true },
  { key: 'issues', label: 'Cảnh báo', right: true },
  { key: 'cost_vnd', label: 'Chi phí', right: true },
  { key: 'wall_seconds', label: 'Thời gian', right: true },
  { key: 'created_at', label: 'Tải lên' },
];

const TH = 'sticky top-0 z-[1] whitespace-nowrap border-b border-strong bg-surface2 px-3 py-2 text-left text-2xs font-medium uppercase tracking-wider text-ink-2';
const TD = 'border-b border-line px-3 py-2 align-middle group-last:border-b-0';

export function HistoryTable({ jobs, sort, onSort, empty, fill }: {
  /** Fill the parent's remaining height and scroll inside (header stays pinned). */
  fill?: boolean;
  jobs: HistoryItem[];
  sort?: Sort;
  onSort?: (key: SortKey) => void;
  empty?: { title: string; text: string };
}) {
  const navigate = useNavigate();
  if (!jobs.length) {
    return <EmptyState title={empty?.title ?? 'Chưa có lượt xử lý nào'}>{empty?.text ?? 'Tải một file PDF lên để bắt đầu.'}</EmptyState>;
  }
  return (
    <div className={cx('overflow-auto', fill && 'min-h-0 flex-1')}>
      <table className="tbl w-full min-w-[860px] border-collapse">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} scope="col" className={cx(TH, c.right && 'text-right')}
                aria-sort={sort?.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                {onSort ? (
                  <button type="button" onClick={() => onSort(c.key)} className="inline-flex cursor-pointer items-center gap-1 uppercase tracking-wider">
                    {c.label}{sort?.key === c.key && <span aria-hidden="true">{sort.dir === 'asc' ? '↑' : '↓'}</span>}
                  </button>
                ) : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={`${j.kind}-${j.id}`} tabIndex={0} onClick={() => navigate(openPath(j))}
              onKeyDown={(e) => { if (e.key === 'Enter') navigate(openPath(j)); }}
              className="group cursor-pointer hover:bg-primary-soft">
              <td className={TD}><Badge tone={j.kind === 'ocr' ? 'info' : 'muted'}>{KIND_LABEL[j.kind]}</Badge></td>
              <td className={TD}><div className="flex items-center gap-2.5"><Icon name="file" /><strong className="font-medium">{j.filename || j.id}</strong></div></td>
              <td className={TD}><StatusBadge status={j.status} /></td>
              <td className={cx(TD, 'text-right font-mono tabular-nums')}>{j.page_count || '—'}</td>
              <td className={cx(TD, 'text-right font-mono tabular-nums')}>{j.status === 'done' ? j.rows : '—'}</td>
              <td className={cx(TD, 'text-right font-mono tabular-nums')}>{j.issues ? <Badge tone="warn">{j.issues}</Badge> : <span className="text-mute">0</span>}</td>
              <td className={cx(TD, 'whitespace-nowrap text-right font-mono tabular-nums')} title={j.cost_usd ? `$${j.cost_usd.toFixed(5)}` : undefined}>{j.cost_vnd ? `${j.cost_vnd.toLocaleString('vi-VN')}đ` : '—'}</td>
              <td className={cx(TD, 'whitespace-nowrap text-right font-mono tabular-nums')}>{j.wall_seconds != null ? `${j.wall_seconds.toFixed(1)}s` : '—'}</td>
              <td className={cx(TD, 'whitespace-nowrap text-mute')}>{fmtTime(j.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
