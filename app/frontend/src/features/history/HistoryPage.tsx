import { useEffect, useMemo, useState } from 'react';
import { useHistory } from '../../api/hooks';
import type { HistoryItem } from '../../api/types';
import { Page } from '../../components/layout/Page';
import { Icon } from '../../components/ui/Icon';
import { EmptyState, Pagination, Panel, Segmented, Skeleton } from '../../components/ui/primitives';
import { useStored } from '../../lib/storage';
import { HistoryTable, type Sort, type SortKey } from './HistoryTable';

type Kind = 'all' | HistoryItem['kind'];
type Status = 'all' | 'ready' | 'processing' | 'review' | 'failed';

/** Every run of both tools in one list: filter by tool, by status, or search by file name. */
export function HistoryPage() {
  const { data, isLoading, error } = useHistory();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<Kind>('all');
  const [status, setStatus] = useState<Status>('all');
  const [sort, setSort] = useState<Sort>({ key: 'created_at', dir: 'desc' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useStored('history-page-size', 10);

  const jobs = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (s: HistoryItem) =>
      (kind === 'all' || s.kind === kind) &&
      (status === 'all' ||
        (status === 'ready' && s.status === 'done') ||
        (status === 'processing' && (s.status === 'pending' || s.status === 'running')) ||
        (status === 'review' && s.status === 'done' && s.issues > 0) ||
        (status === 'failed' && s.status === 'failed'));
    const list = (data ?? []).filter((j) => match(j) && (!q || j.filename.toLowerCase().includes(q)));
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const x = a[sort.key] ?? 0, y = b[sort.key] ?? 0; // runs that have not finished have no cost / time yet
      return (typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number)) * dir;
    });
  }, [data, query, kind, status, sort]);

  useEffect(() => setPage(1), [query, kind, status, sort, pageSize]);
  const pages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const current = Math.min(page, pages); // the list can shrink while polling
  const visible = jobs.slice((current - 1) * pageSize, current * pageSize);

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'filename' || key === 'kind' ? 'asc' : 'desc' }));

  return (
    <Page crumbs={[{ label: 'Lịch sử' }]} fill>
      <div className="flex flex-none flex-wrap items-center gap-2.5">
        <div className="search relative min-w-0 flex-[1_1_220px] sm:flex-[0_1_320px]">
          <span className="pointer-events-none absolute left-2.5 top-[7px] text-mute"><Icon name="search" size={16} /></span>
          <input type="search" placeholder="Tìm theo tên file" aria-label="Tìm theo tên file" value={query} onChange={(e) => setQuery(e.target.value)}
            className="h-8 w-full rounded-md border border-strong bg-white pl-8 pr-2 hover:border-mute focus:border-primary focus:outline-none focus:shadow-ring" />
        </div>
        <Segmented<Kind> label="Lọc theo công cụ" value={kind} onChange={setKind} options={[
          { value: 'all', label: 'Tất cả' }, { value: 'steel', label: 'Phân tích bản vẽ' }, { value: 'ocr', label: 'Trích xuất bảng' },
        ]} />
        <Segmented<Status> label="Lọc theo trạng thái" value={status} onChange={setStatus} options={[
          { value: 'all', label: 'Mọi trạng thái' }, { value: 'ready', label: 'Hoàn tất' }, { value: 'processing', label: 'Đang xử lý' },
          { value: 'review', label: 'Cần soát' }, { value: 'failed', label: 'Lỗi' },
        ]} />
        <span className="flex-1" />
        <span className="font-mono text-xs text-mute">{jobs.length} / {data?.length ?? 0}</span>
      </div>
      <Panel fill label="Danh sách lượt xử lý">
        {isLoading ? <div className="grid gap-3 p-4"><Skeleton h={20} /><Skeleton h={20} /><Skeleton h={20} /></div>
          : error ? <EmptyState title="Không tải được lịch sử">{(error as Error).message}</EmptyState>
          : <HistoryTable fill jobs={visible} sort={sort} onSort={onSort}
              empty={data?.length ? { title: 'Không có kết quả phù hợp', text: 'Thử đổi từ khóa hoặc bộ lọc.' } : undefined} />}
        {!isLoading && !error && jobs.length > 0 && (
          <Pagination page={current} pageSize={pageSize} total={jobs.length} onPage={setPage} onPageSize={setPageSize} />
        )}
      </Panel>
    </Page>
  );
}
