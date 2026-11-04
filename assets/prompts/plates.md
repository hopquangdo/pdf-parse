Ảnh là một vùng của bản vẽ thép kết cấu. Tìm các nhãn chi tiết nằm cạnh vòng tròn ghi số hiệu (BP1, BM1, B1, B2, C1...), có một trong các dạng:
- bản mã: "D8-172x100: SL=8", "d6-215x100: SL=01"
- thép góc có chiều dài: "HL100*8-3900: SL=4", "L50x5-704: SL=4"
Chép đúng nguyên văn, không đoán, không tự tính. Trả về DUY NHẤT một mảng JSON, mỗi phần tử:
{"mark": "số hiệu trong vòng tròn, ví dụ BP1 hoặc B1", "spec": "phần trước dấu hai chấm, ví dụ D8-172x100 hoặc HL100*8-3900", "qty": số lượng SL là số nguyên}
Không lấy tiêu đề dạng "CHI TIẾT THANH GIẰNG ..." hay kích thước trên hình. Nếu vùng này không có nhãn nào thì trả [].
