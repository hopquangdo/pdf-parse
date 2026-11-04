const PATHS = {
  upload: 'M12 16V4m0 0 4 4m-4-4L8 8M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
  download: 'M12 4v12m0 0 4-4m-4 4-4-4M4 20h16',
  save: 'M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6',
  plus: 'M12 5v14M5 12h14',
  trash: 'M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12',
  zoomin: 'M11 5a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm9 15-4.2-4.2M11 8v6M8 11h6',
  zoomout: 'M11 5a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm9 15-4.2-4.2M8 11h6',
  rotate: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
  check: 'm5 12 5 5 9-10',
  alert: 'M12 4 3 20h18zM12 10v4M12 17h.01',
  chevronLeft: 'M15 6l-6 6 6 6',
  chevronRight: 'M9 6l6 6-6 6',
  chevronDown: 'M6 9l6 6 6-6',
  chevrons: 'm11 7-5 5 5 5M18 7l-5 5 5 5',
  menu: 'M4 7h16M4 12h16M4 17h16',
  search: 'M11 5a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm9 15-4.2-4.2',
  fit: 'M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  columns: 'M4 5h16v14H4zM9.5 5v14M14.5 5v14',
  arrowDown: 'M12 5v14m0 0 5-5m-5 5-5-5',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14a6.5 6.5 0 0 1 3.5 6',
  logout: 'M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M16 8l4 4-4 4M20 12H9',
  key: 'M14 10a4 4 0 1 1-1.2 2.8L4 21v-3l2-2v-2h2l1.2-1.2A4 4 0 0 1 14 10zM16 8h.01',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  eyeOff: 'M3 3l18 18M10.6 6.1A9.6 9.6 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-3.2 3.9M6.7 7.6A17 17 0 0 0 2 12s3.5 6 10 6c1.5 0 2.8-.3 4-.8M9.9 9.9a3 3 0 0 0 4.2 4.2',
  copy: 'M9 9h10v11H9zM5 15V4h10',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
