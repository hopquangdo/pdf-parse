import type { ReactNode } from 'react';

/** Full-page frame for the sign-in and forced-password-change screens (no app chrome, no navigation). */
export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-app px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span aria-hidden="true" className="grid size-9 place-items-center rounded-md bg-primary text-white">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M7 19V6h11M7 12.5h8" /></svg>
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-medium text-ink">Steel Takeoff</div>
            <div className="text-2xs uppercase tracking-wider text-mute">Bóc tách bản vẽ</div>
          </div>
        </div>
        <section className="rounded-lg border border-line bg-white p-6 shadow-pop">
          <h1 className="text-xl font-medium text-ink">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-mute">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </section>
        {footer && <div className="mt-4 text-center text-xs text-mute">{footer}</div>}
      </div>
    </main>
  );
}
