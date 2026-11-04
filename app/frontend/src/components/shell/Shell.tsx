import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link, NavLink, Outlet, useLocation, useMatches } from 'react-router-dom';
import { useHealth } from '../../api/hooks';
import { useAuth, useUser } from '../../auth/AuthProvider';
import { ChangePasswordDialog } from '../../features/auth/ChangePasswordDialog';
import { cx } from '../../lib/cx';
import { useStored } from '../../lib/storage';
import { Icon } from '../ui/Icon';
import { Button, IconButton } from '../ui/primitives';

interface Slots { crumbs: HTMLElement | null; actions: HTMLElement | null }
const SlotContext = createContext<Slots>({ crumbs: null, actions: null });

/** Pages describe the breadcrumb and top-bar actions; the shell owns where they render. */
export function Crumbs({ items }: { items: { label: string; to?: string }[] }) {
  const { crumbs } = useContext(SlotContext);
  if (!crumbs) return null;
  return createPortal(
    items.map((it, i) => (
      <span key={i} className="contents">
        {i > 0 && <span aria-hidden="true" className="text-strong">/</span>}
        {it.to ? <Link to={it.to}>{it.label}</Link> : <strong className="truncate font-medium text-ink">{it.label}</strong>}
      </span>
    )),
    crumbs,
  );
}

export function TopbarActions({ children }: { children: ReactNode }) {
  const { actions } = useContext(SlotContext);
  return actions ? createPortal(children, actions) : null;
}

// `label` / `group-data-*` hide text only when the sidebar is collapsed on wide screens; the mobile drawer always shows it.
const COLLAPSE_HIDE = 'md:group-data-[collapsed=true]:hidden';
const COLLAPSE_CENTER = 'md:group-data-[collapsed=true]:justify-center md:group-data-[collapsed=true]:px-0';

export function Shell() {
  const [collapsed, setCollapsed] = useStored('sidebar-collapsed', false);
  const [drawer, setDrawer] = useState(false);
  const [slots, setSlots] = useState<Slots>({ crumbs: null, actions: null });
  const { pathname } = useLocation();
  const flush = useMatches().some((m) => (m.handle as { flush?: boolean } | undefined)?.flush);
  const health = useHealth();
  const user = useUser();
  const { logout } = useAuth();
  const [changingPassword, setChangingPassword] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const away = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc); };
  }, [menuOpen]);

  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setCollapsed(!collapsed);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [collapsed, setCollapsed]);

  const historyActive = pathname.startsWith('/jobs');
  const analyseActive = pathname === '/' || pathname.startsWith('/job/');
  const extractActive = pathname.startsWith('/extract');
  const navCls = (active: boolean) => cx(
    'nav-item flex h-[34px] items-center gap-2.5 border-l-[3px] px-3.5 font-medium', COLLAPSE_CENTER,
    active ? 'border-l-primary bg-primary-soft text-primary' : 'border-l-transparent text-ink-2 hover:bg-surface',
  );

  return (
    <div data-collapsed={collapsed} data-drawer={drawer}
      className={cx('app group grid h-dvh grid-cols-[212px_minmax(0,1fr)] transition-[grid-template-columns] duration-200 data-[collapsed=true]:grid-cols-[52px_minmax(0,1fr)] max-md:!grid-cols-1',
        collapsed && 'collapsed', drawer && 'drawer-open')}>
      <a href="#main" className="fixed -top-12 left-3 z-[100] bg-primary px-4 py-2 text-white focus:top-3">Bỏ qua điều hướng</a>
      <aside aria-label="Điều hướng chính"
        className={cx('flex flex-col overflow-hidden whitespace-nowrap border-r border-strong bg-white',
          'max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-30 max-md:w-[min(260px,86vw)] max-md:-translate-x-full max-md:shadow-modal max-md:transition-transform',
          drawer && 'max-md:translate-x-0')}>
        <Link to="/" title="Steel Takeoff"
          className={cx('flex h-11 flex-none items-center gap-2.5 border-b border-strong bg-chrome px-3 text-ink hover:no-underline', COLLAPSE_CENTER)}>
          <span aria-hidden="true" className="grid size-[26px] flex-none place-items-center bg-primary text-white">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M7 19V6h11M7 12.5h8" /></svg>
          </span>
          <span className={cx('font-medium leading-tight', COLLAPSE_HIDE)}>
            Steel Takeoff
            <small className="block text-2xs font-medium uppercase tracking-wider text-mute">Bóc tách bản vẽ</small>
          </span>
        </Link>
        <nav className="flex flex-col py-2">
          <NavLink to="/" end className={() => navCls(analyseActive)} title="Phân tích bản vẽ"><Icon name="columns" /><span className={cx('label', COLLAPSE_HIDE)}>Phân tích bản vẽ</span></NavLink>
          <NavLink to="/extract" className={() => navCls(extractActive)} title="Trích xuất bảng"><Icon name="grid" /><span className={cx('label', COLLAPSE_HIDE)}>Trích xuất bảng</span></NavLink>
          <NavLink to="/jobs" className={() => navCls(historyActive)} title="Lịch sử"><Icon name="folder" /><span className={cx('label', COLLAPSE_HIDE)}>Lịch sử</span></NavLink>
        </nav>
        <div className="mt-auto flex flex-col border-t border-line">
          <div title="Trạng thái hệ thống" className={cx('flex items-center gap-1.5 px-3.5 py-2 text-2xs uppercase tracking-wide text-mute', COLLAPSE_CENTER)}>
            <span className={cx('size-2 flex-none rounded-full', health.isError ? 'bg-[#d1242f] shadow-[0_0_0_2px_#fbdcda]' : health.data?.ok ? 'bg-[#2da44e] shadow-[0_0_0_2px_#d4f0dc]' : 'bg-strong')} />
            <span className={COLLAPSE_HIDE}>{health.isError ? 'Không kết nối được máy chủ' : health.data?.ok ? 'Hệ thống hoạt động' : 'Đang kiểm tra…'}</span>
          </div>
          <Button variant="ghost" size="sm" aria-expanded={!collapsed} title={`${collapsed ? 'Mở rộng' : 'Thu gọn'} thanh bên (Ctrl+B)`}
            onClick={() => setCollapsed(!collapsed)}
            className={cx('collapse-btn m-1.5 justify-start max-md:hidden', COLLAPSE_CENTER)}>
            <span className={cx('transition-transform', collapsed && 'rotate-180')}><Icon name="chevrons" size={16} /></span>
            <span className={cx('label', COLLAPSE_HIDE)}>Thu gọn</span>
          </Button>
        </div>
      </aside>
      <ChangePasswordDialog open={changingPassword} onClose={() => setChangingPassword(false)} />
      <div onClick={() => setDrawer(false)} aria-hidden="true"
        className="scrim fixed inset-0 z-[29] hidden bg-black/45 max-md:group-data-[drawer=true]:block" />
      <div className="flex h-dvh min-w-0 flex-col">
        <header className="flex h-11 flex-none items-center justify-between gap-3 border-b border-strong bg-white px-3 shadow-[inset_0_3px_0_theme(colors.primary.DEFAULT)] sm:px-4 lg:px-5">
          <div className="flex min-w-0 items-center gap-1.5">
            <IconButton className="menu-btn md:hidden" icon="menu" label="Mở menu" size="md" onClick={() => setDrawer(true)} />
            <div className="crumbs flex min-w-0 items-center gap-1.5 text-mute" ref={(el) => setSlots((s) => (s.crumbs === el || !el ? s : { ...s, crumbs: el }))} />
          </div>
          <div className="flex flex-none items-center gap-3">
            <div className="topbar-actions flex flex-none items-center gap-1.5" ref={(el) => setSlots((s) => (s.actions === el || !el ? s : { ...s, actions: el }))} />
            <div ref={menuRef} className="relative border-l border-line pl-3">
              <button type="button" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}
                title={`${user.name || user.email} (${user.role})`}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-surface2">
                <span aria-hidden="true" className="grid size-6 place-items-center rounded-full bg-primary-soft text-2xs font-medium text-primary">
                  {(user.name || user.email).charAt(0).toUpperCase()}
                </span>
                <span className="hidden max-w-[140px] truncate text-xs text-ink-2 sm:inline">{user.name || user.email}</span>
                <Icon name="chevronDown" size={14} />
              </button>
              {menuOpen && (
                <div role="menu" className="absolute right-0 top-full z-40 mt-1 w-[200px] rounded-md border border-strong bg-white py-1 shadow-modal">
                  <div className="truncate border-b border-line px-3 py-1.5 text-2xs text-mute">{user.email}</div>
                  <button role="menuitem" type="button" className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-surface"
                    onClick={() => { setMenuOpen(false); setChangingPassword(true); }}><Icon name="key" size={16} />Đổi mật khẩu</button>
                  <button role="menuitem" type="button" className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-surface"
                    onClick={() => { setMenuOpen(false); void logout(); }}><Icon name="logout" size={16} />Đăng xuất</button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main id="main" tabIndex={-1} className={cx('min-h-0 flex-1 bg-app outline-none', flush ? 'overflow-hidden' : 'overflow-auto')}>
          <SlotContext.Provider value={slots}>
            <Outlet />
          </SlotContext.Provider>
        </main>
      </div>
    </div>
  );
}
