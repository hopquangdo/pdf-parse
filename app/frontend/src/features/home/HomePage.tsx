import { ToolLanding } from './ToolLanding';

/** Phân tích bản vẽ: read a steel drawing and compute its quantities. */
export function HomePage() {
  return (
    <ToolLanding kind="steel" name="Phân tích bản vẽ" dropTitle="Kéo thả bản vẽ PDF vào đây"
      steps={['Tải bản vẽ kỹ thuật dạng PDF', 'Hệ thống đọc các bảng thép và tính khối lượng', 'Soát lại rồi xuất vào file Excel mẫu']} />
  );
}
