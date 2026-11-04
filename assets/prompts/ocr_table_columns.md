Ảnh là {part}. {header_note}
Bảng có các cột sau (theo thứ tự trái sang phải trên ảnh): {columns}.
Chép lại từng dòng của bảng, từ trên xuống dưới, đúng nguyên văn từng ô (giữ dấu tiếng Việt, số, dấu phẩy và dấu chấm trong số, đơn vị). Không đoán, không tính toán, không bỏ dòng.
Quy tắc:
- Mỗi dòng là một đối tượng JSON có khóa là TÊN CỘT ở trên (đúng nguyên văn); ô trống thì để chuỗi rỗng "".
- Một giá trị bị chia thành nhiều ô nhỏ trên ảnh (ví dụ "60 x 5,5" nằm ở 3 ô) thì gộp thành một giá trị trong cột của nó.
- Dòng tiêu đề của một nhóm (chữ in đậm trải qua nhiều cột, ví dụ "KIM THU SÉT (1CK)") đặt chữ vào cột đầu tiên có chữ của dòng đó, kèm các tổng ở các cột tương ứng.
Trả về DUY NHẤT một đối tượng JSON: {"rows": [ {"<tên cột 1>": "...", "<tên cột 2>": "...", ...}, ... ]}
