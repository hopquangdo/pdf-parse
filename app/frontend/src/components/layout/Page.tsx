import type { ReactNode } from 'react';
import { cx } from '../../lib/cx';
import { Crumbs } from '../shell/Shell';

interface PageProps {
  /** Breadcrumb shown in the top bar: tool / page. */
  crumbs: { label: string; to?: string }[];
  /** Buttons, right-aligned above the content. */
  actions?: ReactNode;
  /** narrow: a centred column for forms; full: the whole width. */
  width?: 'narrow' | 'full';
  /** Fill the screen height and let the children scroll inside (tables, viewers). */
  fill?: boolean;
  children: ReactNode;
}

/** The one frame every ordinary page uses: breadcrumb, optional actions, and content with the same spacing. */
export function Page({ crumbs, actions, width = 'full', fill, children }: PageProps) {
  return (
    <div className={cx('page flex flex-col gap-3.5 p-3 sm:p-4 lg:p-5', fill && 'h-full min-h-0')}>
      <Crumbs items={crumbs} />
      <div className={cx('flex min-w-0 flex-col gap-3.5', width === 'narrow' && 'mx-auto w-full max-w-[760px]', fill && 'min-h-0 flex-1')}>
        {actions && <div className="flex flex-none flex-wrap items-center justify-end gap-1.5">{actions}</div>}
        {children}
      </div>
    </div>
  );
}
