import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useCatalog, useJob } from '../../api/hooks';
import type { Job } from '../../api/types';
import { Crumbs } from '../../components/shell/Shell';
import { Icon } from '../../components/ui/Icon';
import { Button, EmptyState, Panel, Skeleton, Spinner } from '../../components/ui/primitives';
import { fmtElapsed } from '../../lib/format';
import { EMPTY_CATALOG } from '../../lib/formulas';
import { Workspace } from './Workspace';

const PAGE = 'page flex flex-col gap-3.5 p-4 lg:p-5';
const CARD = 'mx-auto my-12 flex w-full max-w-[560px] flex-col items-center gap-3.5 p-8 text-center';

function Processing({ job }: { job: Job }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className={PAGE}>
      <Crumbs items={[{ label: 'Lịch sử', to: '/jobs' }, { label: job.filename }]} />
      <Panel className={CARD} label="Đang xử lý">
        <div role="status" className="flex w-full flex-col items-center gap-3.5">
          <Spinner className="size-6" />
          <strong className="text-[14px]">Đang đọc bản vẽ…</strong>
          <span className="text-mute">Hệ thống đang nhận diện các vùng và đọc số liệu. Bạn có thể rời trang này, kết quả được lưu tự động.</span>
          <div className="h-1.5 w-full overflow-hidden bg-surface2"><i className="block h-full w-[35%] animate-slide bg-primary" /></div>
          <span className="font-mono text-xs tabular-nums text-mute">Đã chạy {fmtElapsed(now - job.created_at)}</span>
        </div>
      </Panel>
    </div>
  );
}

export function ReviewPage() {
  const { id = '' } = useParams();
  const { data: job, isLoading, error } = useJob(id);
  const catalog = useCatalog();

  if (isLoading || (job?.status === 'done' && catalog.isLoading)) {
    return <div className={PAGE}><Panel className="grid gap-3 p-4"><Skeleton h={24} w="40%" /><Skeleton h={200} /></Panel></div>;
  }
  if (error || !job) {
    return (
      <div className={PAGE}>
        <Crumbs items={[{ label: 'Lịch sử', to: '/jobs' }, { label: 'Không tìm thấy' }]} />
        <Panel><EmptyState title="Không mở được bản vẽ này">{(error as Error | null)?.message ?? 'Lỗi không xác định'}</EmptyState></Panel>
      </div>
    );
  }
  if (job.status === 'pending' || job.status === 'running') return <Processing job={job} />;
  if (job.status === 'failed') {
    return (
      <div className={PAGE}>
        <Crumbs items={[{ label: 'Lịch sử', to: '/jobs' }, { label: job.filename }]} />
        <Panel className={CARD} label="Lỗi">
          <div role="alert" className="flex flex-col items-center gap-3.5">
            <Icon name="alert" size={32} />
            <strong className="text-[14px]">Không đọc được bản vẽ này</strong>
            <span className="text-mute">{job.error ?? 'Đã xảy ra lỗi không xác định.'}</span>
            <Link to="/" className="inline-flex h-[30px] items-center rounded border border-strong bg-white px-3 text-xs font-medium text-ink hover:bg-surface2 hover:no-underline">Tải bản vẽ khác</Link>
          </div>
        </Panel>
      </div>
    );
  }
  if (catalog.isError) {
    return (
      <div className={PAGE}>
        <Crumbs items={[{ label: 'Lịch sử', to: '/jobs' }, { label: job.filename }]} />
        <Panel>
          <EmptyState title="Không tải được bảng tra" action={<Button onClick={() => void catalog.refetch()}>Thử lại</Button>}>
            Bảng đơn trọng lấy từ file Excel mẫu; thiếu bảng này thì không tính được khối lượng.
          </EmptyState>
        </Panel>
      </div>
    );
  }
  return <Workspace key={job.id} job={job} catalog={catalog.data ?? EMPTY_CATALOG} />;
}
