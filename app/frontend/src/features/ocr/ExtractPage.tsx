import { ToolLanding } from '../home/ToolLanding';

/** Trích xuất bảng: any table in a PDF or scan becomes an Excel sheet. */
export function ExtractPage() {
  return (
    <ToolLanding kind="ocr" name="Trích xuất bảng" dropTitle="Kéo thả file PDF có bảng vào đây"
      steps={['Tải file PDF hoặc bản scan có bảng', 'Tích các trang cần trích xuất', 'Xem kết quả và tải file Excel (mỗi trang một sheet)']} />
  );
}
