from src.domain.steel_members import angle_rows_to_members, parse_angle, parse_plate, plate_to_member, section_from_title


def test_section_from_title():
    assert section_from_title("CHI TIẾT BẢN MÃ ĐOẠN CỘT B") == "ĐOẠN B"
    assert section_from_title("ĐOẠN CỘT C") == "ĐOẠN C"
    assert section_from_title("CHI TIẾT KIM THU SÉT") == "KIM THU SÉT"


def test_angle_and_plate_specs():
    assert parse_angle("THÉP L50x5") == (50, 5)
    assert parse_plate("D8-172x100") == {"t": 8, "len": 172, "w": 100}
    assert plate_to_member("ĐOẠN B", "BP4", "D5-50x50", 6) == {
        "section": "ĐOẠN B", "mark": "BP4", "type": "d", "w": 50, "t": 5, "len": 50, "qty": 6}


def test_joined_mark_is_split_into_two_bars_with_half_the_quantity():
    rows = [{"mark": "B3-B3a", "L": 365, "qty": 8}, {"mark": "B7", "L": 1074, "qty": 8}]
    out = angle_rows_to_members("ĐOẠN B", "THÉP L50x5", rows)
    assert [(m["mark"], m["qty"], m["len"]) for m in out] == [("B3", 4, 365), ("B3a", 4, 365), ("B7", 8, 1074)]
    assert all(m["type"] == "L" and m["w"] == 50 and m["t"] == 5 for m in out)


def test_angle_bar_callouts_with_length():
    assert plate_to_member("ĐOẠN B", "B1", "HL100*8-3900", 4) == {
        "section": "ĐOẠN B", "mark": "B1", "type": "L", "w": 100, "t": 8, "len": 3900, "qty": 4}
    assert plate_to_member("ĐOẠN B", "B2", "L50x5-704", 4)["len"] == 704
    assert plate_to_member("ĐOẠN B", "BP1", "D8-172x100", 8)["type"] == "d"
