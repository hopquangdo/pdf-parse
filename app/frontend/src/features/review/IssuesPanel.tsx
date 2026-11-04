import { useState } from 'react';
import type { Issue } from '../../api/types';
import { Icon } from '../../components/ui/Icon';
import { cx } from '../../lib/cx';

export function IssuesPanel({ issues, onSelect }: { issues: Issue[]; onSelect: (mark: string) => void }) {
  const [open, setOpen] = useState(true);
  const list = issues.filter((i) => i.level !== 'info');
  if (!list.length) return null;
  return (
    <section aria-label="Cảnh báo" className="issues border-b border-warn-line bg-warn-soft">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-2xs font-medium uppercase tracking-wider text-warn">
        <Icon name={open ? 'chevronDown' : 'chevronRight'} size={14} /> Cảnh báo ({list.length})
      </button>
      {open && (
        <ul className="m-0 max-h-[132px] list-none overflow-auto px-2.5 pb-2.5">
          {list.map((i, k) => (
            <li key={k} className="flex gap-1.5 py-0.5 text-xs text-[#78350f]">
              <span className={cx('flex-none font-medium', i.level === 'error' && 'text-danger')}>{i.level === 'error' ? 'Lỗi' : 'Cảnh báo'}</span>
              {i.mark ? (
                <button type="button" onClick={() => onSelect(i.mark as string)} className="flex cursor-pointer gap-1.5 text-left hover:underline">
                  <strong>{i.mark}</strong><span>{i.message}</span>
                </button>
              ) : <span>{i.message}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
