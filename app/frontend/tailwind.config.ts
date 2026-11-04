import type { Config } from 'tailwindcss';

/**
 * Modern light theme: soft neutral canvas, white rounded panels, hairline borders, Inter type and pill status badges.
 * All design tokens live here, nowhere else.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    screens: { sm: '600px', md: '900px', lg: '1100px' },
    extend: {
      colors: {
        app: '#f6f7f9',        // canvas behind the panels
        chrome: '#fafbfc',     // panel header strips, toolbars
        surface: '#f9fafb',
        surface2: '#f1f3f5',
        line: '#e5e7eb',
        strong: '#d1d5db',     // stronger rules / control borders
        ink: { DEFAULT: '#111827', 2: '#374151' },
        mute: '#6b7280',
        primary: { DEFAULT: '#2563eb', hover: '#1d4ed8', press: '#1e40af', soft: '#eff6ff', line: '#bfdbfe' },
        ok: { DEFAULT: '#15803d', soft: '#f0fdf4', line: '#bbf7d0' },
        warn: { DEFAULT: '#b45309', soft: '#fffbeb', line: '#fde68a', led: '#f59e0b' },
        danger: { DEFAULT: '#dc2626', hover: '#b91c1c', soft: '#fef2f2', line: '#fecaca' },
      },
      fontFamily: {
        sans: ['Inter', '"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['"Cascadia Mono"', '"JetBrains Mono"', 'Consolas', '"SFMono-Regular"', 'Menlo', 'monospace'],
      },
      fontSize: { '2xs': ['11px', '1.4'], xs: ['12px', '1.5'], sm: ['13px', '1.5'], base: ['14px', '1.5'] },
      borderRadius: { DEFAULT: '6px', sm: '4px', md: '8px', lg: '12px' },
      boxShadow: {
        panel: '0 1px 2px rgba(16,24,40,.04)',
        pop: '0 4px 16px rgba(16,24,40,.12)',
        modal: '0 16px 40px rgba(16,24,40,.22)',
        ring: '0 0 0 3px rgba(37,99,235,.25)',
      },
      keyframes: {
        slide: { from: { marginLeft: '-35%' }, to: { marginLeft: '100%' } },
        shimmer: { to: { backgroundPosition: '-200% 0' } },
        pop: { from: { opacity: '0', transform: 'translateY(6px)' } },
        flash: { from: { background: '#fde68a' } },
      },
      animation: { slide: 'slide 1.3s ease-in-out infinite', shimmer: 'shimmer 1.2s infinite', pop: 'pop .16s ease-out', flash: 'flash 1.4s ease-out' },
    },
  },
  plugins: [],
} satisfies Config;
