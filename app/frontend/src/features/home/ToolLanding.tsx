import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useHistory } from '../../api/hooks';
import type { HistoryItem } from '../../api/types';
import { Page } from '../../components/layout/Page';
import { FileDropzone } from '../../components/ui/FileDropzone';
import { EmptyState, Kpi, Panel, Skeleton } from '../../components/ui/primitives';
import { HistoryTable } from '../history/HistoryTable';
import { UploadDialog } from './UploadDialog';

/** The entry page of one tool: KPIs of its runs, a drop zone that opens the options popup, and its recent runs. */
export function ToolLanding({ kind, name, dropTitle, steps }: {
  kind: HistoryItem['kind'];
  /** Tool name for the breadcrumb and panel titles. */
  name: string;
  dropTitle: string;
  steps: string[];
}) {
  const { data, isLoading, error } = useHistory();
  const [file, setFile] = useState<File | null>(null);
  const jobs = (data ?? []).filter((j) => j.kind === kind);
  const processing = jobs.filter((j) => j.status === 'pending' || j.status === 'running').length;
  const needsReview = jobs.filter((j) => j.status === 'done' && j.issues > 0).length;
  const value = (n: number) => (isLoading ? '–' : n);

  return (
    <Page crumbs={[{ label: name }]}>
      <div className="kpis grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fit,minmax(170px,1fr))]">
        <Kpi label="Lượt xử lý" value={value(jobs.length)} />
        <Kpi label="Hoàn tất" value={value(jobs.filter((j) => j.status === 'done').length)} tone="ok" />
        <Kpi label="Đang xử lý" value={value(processing)} />
        <Kpi label="Cần soát" value={value(needsReview)} tone={needsReview ? 'warn' : undefined} />
      </div>
      <div className="home-grid grid items-start gap-3.5 lg:grid-cols-[minmax(360px,5fr)_minmax(0,7fr)]">
        <Panel title={name} label={`${name}: tải file lên`}>
          <div className="p-3.5">
            <FileDropzone onFile={setFile} title={dropTitle} />
            <ol className="mt-3.5 flex flex-col gap-1 text-xs text-mute">
              {steps.map((s, i) => <li key={s}>{i + 1}. {s}</li>)}
            </ol>
          </div>
        </Panel>
        <Panel title="Gần đây" actions={<Link to="/jobs" className="text-xs font-medium">Xem lịch sử</Link>}>
          {isLoading ? <div className="grid gap-3 p-4"><Skeleton h={20} /><Skeleton h={20} /></div>
            : error ? <EmptyState title="Không tải được danh sách">{(error as Error).message}</EmptyState>
            : <HistoryTable jobs={jobs.slice(0, 6)} empty={{ title: 'Chưa có lượt xử lý nào', text: 'Tải một file PDF lên để bắt đầu.' }} />}
        </Panel>
      </div>
      <UploadDialog mode={kind} file={file} onClose={() => setFile(null)} />
    </Page>
  );
}
