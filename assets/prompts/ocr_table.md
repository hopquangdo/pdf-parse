Ảnh là {part}. {header_note}{columns_note}
Chép lại bảng thành các dòng, từ trên xuống dưới, đúng nguyên văn từng ô (giữ dấu tiếng Việt, số, dấu phẩy và dấu chấm trong số, đơn vị). Không đoán, không tính toán, không bỏ dòng, không bỏ ô.
Quy tắc:
- Dòng tiêu đề cột (nếu ảnh có) là dòng đầu tiên và PHẢI được chép (trừ khi được dặn khác). Một dòng chữ đứng riêng làm tên bảng ở phía trên thì chép thành một dòng chỉ có ô đầu tiên, các ô còn lại "".
- Mỗi dòng của bảng là một mảng các ô theo thứ tự cột từ trái sang phải. Mọi dòng phải có cùng số phần tử bằng số cột của bảng.
- Ô trống thì để chuỗi rỗng "".
- Ô gộp (một chữ trải qua nhiều cột, ví dụ dòng tiêu đề nhóm): đặt chữ vào ô đầu tiên của vùng gộp, các ô còn lại để "".
- Ô gộp theo chiều dọc: chỉ ghi giá trị ở dòng đầu của vùng gộp, các dòng dưới để "".
Trả về DUY NHẤT một đối tượng JSON: {"columns": số cột, "rows": [["ô 1", "ô 2", ...], ...]}
