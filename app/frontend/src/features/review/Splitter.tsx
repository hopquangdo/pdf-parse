import { cx } from '../../lib/cx';
import { Icon } from '../../components/ui/Icon';
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type RefObject } from 'react';
import { createPortal } from 'react-dom';

const MIN_LEFT = 300;
const MIN_RIGHT = 460;

/** Draggable, keyboard-operable divider. Reports the left pane width in px (null = default split). */
export function Splitter({ container, width, onChange, layout, onLayout, className }: {
  className?: string;
  layout: 'split' | 'table' | 'drawing';
  onLayout: (l: 'split' | 'table' | 'drawing') => void;
  container: RefObject<HTMLElement>;
  width: number | null;
  onChange: (px: number | null) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const max = () => Math.max(MIN_LEFT, (container.current?.clientWidth ?? 1200) - MIN_RIGHT);
  const clamp = (px: number) => Math.min(max(), Math.max(MIN_LEFT, px));
  const startX = useRef(0);
  const startW = useRef(0);

  const current = () => width ?? Math.round((container.current?.clientWidth ?? 1200) * 0.44);

  const collapsed = layout !== 'split';
  const line = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  // The grips are portalled to <body> and positioned over the line, so nothing (sidebar, grid, overflow clipping) can cover or cut them.
  useEffect(() => {
    const measure = () => {
      const r = line.current?.getBoundingClientRect();
      setAt(r && (r.width || r.height) ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null); // hidden on small screens
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (line.current) ro.observe(line.current);
    if (container.current) ro.observe(container.current);
    window.addEventListener('resize', measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [container, layout, width]);
  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    if (collapsed) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    startX.current = e.clientX;
    startW.current = current();
    setDragging(true);
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (dragging) onChange(clamp(startW.current + e.clientX - startX.current));
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); onChange(clamp(current() - 24)); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); onChange(clamp(current() + 24)); }
    else if (e.key === 'Home' || e.key === 'Enter') { e.preventDefault(); onChange(null); }
  };

  const grip = 'grid size-5 place-items-center rounded-full border border-line bg-white text-mute shadow-panel transition-colors hover:border-primary hover:bg-primary hover:text-white';
  return (
    <div ref={line} className={cx('splitter relative w-px touch-none bg-line transition-colors after:absolute after:-inset-x-1 after:inset-y-0 after:content-[""] hover:bg-primary focus-visible:bg-primary focus-visible:outline-none', collapsed ? 'cursor-default' : 'cursor-col-resize', dragging && 'bg-primary', className)} role="separator" aria-orientation="vertical" tabIndex={0}
      aria-label="Đổi kích thước khung (phím mũi tên; Home để đặt lại)" aria-valuemin={MIN_LEFT} aria-valuemax={max()} aria-valuenow={current()}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => setDragging(false)} onPointerCancel={() => setDragging(false)}
      onDoubleClick={() => onChange(null)} onKeyDown={onKey}>
      {at && createPortal(collapsed ? (
        // Collapsed: one large tab hugging the window edge so it is easy to find and hit.
        <button type="button" onClick={() => onLayout('split')} style={{ left: at.x, top: at.y }}
          aria-label={layout === 'drawing' ? 'Hiện bảng' : 'Hiện bản vẽ'} title={layout === 'drawing' ? 'Hiện bảng' : 'Hiện bản vẽ'}
          className={cx('fixed z-[1000] flex h-24 w-7 -translate-y-1/2 flex-col items-center justify-center gap-1.5 border border-line bg-white text-xs font-medium text-ink-2 shadow-pop transition-colors hover:border-primary hover:bg-primary hover:text-white',
            layout === 'drawing' ? '-translate-x-full rounded-l-lg border-r-0' : 'rounded-r-lg border-l-0')}>
          <Icon name={layout === 'drawing' ? 'chevronLeft' : 'chevronRight'} size={14} />
          <span className="[writing-mode:vertical-rl]">{layout === 'drawing' ? 'Bảng' : 'Bản vẽ'}</span>
        </button>
      ) : (
        <div className="fixed z-[1000] flex -translate-x-1/2 -translate-y-1/2 flex-col gap-1" style={{ left: at.x, top: at.y }}
          onPointerDown={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
          <button type="button" className={grip} onClick={() => onLayout('drawing')} aria-label="Thu gọn bảng" title="Thu gọn bảng">
            <Icon name="chevronRight" size={12} />
          </button>
          <button type="button" className={grip} onClick={() => onLayout('table')} aria-label="Thu gọn bản vẽ" title="Thu gọn bản vẽ">
            <Icon name="chevronLeft" size={12} />
          </button>
        </div>
      ), document.body)}
    </div>
  );
}
