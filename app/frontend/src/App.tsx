import { createHashRouter } from 'react-router-dom';
import { RequireAuth } from './components/shell/RequireAuth';
import { EmptyState, Panel } from './components/ui/primitives';
import { LoginPage } from './features/auth/LoginPage';
import { HistoryPage } from './features/history/HistoryPage';
import { HomePage } from './features/home/HomePage';

// Hash routing keeps deep links working when the SPA is served as static files under /app/.
export const router = createHashRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'jobs', element: <HistoryPage />, handle: { flush: true } }, // only the table scrolls
      { path: 'extract', lazy: async () => ({ Component: (await import('./features/ocr/ExtractPage')).ExtractPage }) }, // pdf.js is heavy
      { path: 'extract/job/:id', handle: { flush: true }, lazy: async () => ({ Component: (await import('./features/ocr/OcrJobPage')).OcrJobPage }) },
      {
        path: 'job/:id',
        handle: { flush: true },
        // pdf.js is heavy: load the review workspace on demand.
        lazy: async () => ({ Component: (await import('./features/review/ReviewPage')).ReviewPage }),
      },
      { path: '*', element: <div className="page p-4 lg:p-5"><Panel><EmptyState title="Không tìm thấy trang">Kiểm tra lại địa chỉ rồi thử lại.</EmptyState></Panel></div> },
    ],
  },
]);
