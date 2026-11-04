Ảnh là một vùng của bản vẽ thép kết cấu (vùng: {label}).
Trích CHỈ các dòng bảng thống kê thanh/bản mã nhìn thấy trong ảnh, đúng nguyên văn số liệu, không đoán.
Trả về DUY NHẤT một mảng JSON, mỗi phần tử:
{"section": "ĐOẠN B", "mark": "B1", "type": "L|d|Ф|M", "w": số, "t": số hoặc "Bộ" hoặc null, "len": số, "qty": số nguyên}
L: thép góc (w=cạnh, t=dày); d: bản mã (w=rộng, t=dày, len=dài); Ф: thép tròn; M: bu lông.
Cặp ghép như B3-B3a có SL=8 thì tách thành B3 (4) và B3a (4). Không thấy dòng nào thì trả [].
