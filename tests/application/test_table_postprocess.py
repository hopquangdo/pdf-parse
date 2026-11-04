from src.application.table_postprocess import expected_unit_weight, fix_words, normalise_number, repair

ANGLES = {"L63x63x5": 4.81, "L75x75x5": 5.8}
HEAD = ["STT", "Mã", "Quy cách", "Số lượng", "C.dài", "Đ.trọng", "Tổng C.dài", "Khối lượng"]


def test_numbers_repair_separators_and_reject_words():
    assert normalise_number("0:032") == "0,032" and normalise_number("0;094") == "0,094" and normalise_number("0.020") == "0,020"
    assert normalise_number("1.849,51") == "1.849,51" and normalise_number("Thép") is None and normalise_number("-") is None


def test_unit_weight_from_the_section():
    assert expected_unit_weight("L63x63x5x470", ANGLES) == 4.81 and expected_unit_weight("L63x5-886", ANGLES) == 4.81
    assert expected_unit_weight("d=8-50x400", ANGLES) == 62.8 and expected_unit_weight("d6x220x90", ANGLES) == 47.1
    assert abs(expected_unit_weight("Ø18x3370", ANGLES) - 1.998) < 0.002          # round bar
    assert abs(expected_unit_weight("Ø27x2,5x1000", ANGLES) - 1.511) < 0.002      # tube
    assert expected_unit_weight("M12x50-2ecuxBộ", ANGLES) is None


def test_rules_repair_one_wrong_number_and_flag_it():
    rows = [HEAD,
            ["1", "T1", "L63x63x5x470", "1", "0,470", "4,81", "10,47", "2,26"],         # total misread (0,47 -> 10,47)
            ["2", "T2", "L63x63x5x470", "1", "0,470", "13:34", "0,470", "2,26"],        # unit weight misread
            ["3", "T3", "d=6-143x142", "10", "0,020", "47,10", "0,20", "9,56"]]
    out, flags = repair(rows, ANGLES)
    assert out[1][6] == "0,47" and (1, 6) in flags                          # total = count x length
    assert out[2][5] == "4,81" and (2, 5) in flags                          # unit weight from the catalog
    assert out[3] == rows[3] and not [k for k in flags if k[0] == 3]          # a right row is left alone


def test_a_blank_cell_stays_blank_and_index_gaps_are_flagged():
    rows = [HEAD, ["1", "T4", "d14xx350", "1", "0,005", "", "0,005", ""], ["3", "T5", "L63x63x5x715", "1", "0,715", "4,81", "0,715", "3,44"]]
    out, flags = repair(rows, ANGLES)
    assert out[1][5] == "" and out[1][7] == ""
    assert (2, 0) in flags                                                  # 1 then 3: a row is missing


def test_words_take_the_trade_spelling():
    assert fix_words("Thép tròn giăng") == "Thép tròn giằng" and fix_words("Bulon M22") == "Bulon M22"


def test_llm_fixer_rereads_only_the_doubtful_cells():
    from PIL import Image
    from src.application.cell_llm_fix import LlmCellFixer

    class Reader:
        def __init__(self): self.calls = 0
        def ask_json(self, png, prompt, label=""):
            self.calls += 1
            return {"1": "Ø16x290", "2": ""}

    grid = [["A", "016x290", "ok"], ["B", "x", "fine"]]
    conf = [[0.99, 0.31, 0.97], [0.98, 0.2, 0.99]]
    fixer = LlmCellFixer(Reader())
    todo = fixer.pick(grid, conf, flagged=set())
    assert todo == [(0, 1), (1, 1)]
    img = Image.new("RGB", (80, 30), "white")
    got = fixer.fix(grid, {p: img for p in todo}, todo)
    assert got == {(0, 1): "Ø16x290"}                       # the empty answer changes nothing


def test_numbers_are_realigned_when_the_header_is_one_column_off():
    head = ["STT", "Quy cách", "Số lượng", "C.dài", "Đ.trọng", "Tổng", "Khối lượng"]
    rows = [head,
            ["1", "L63x63x5x470", "T1", "2", "1,5", "4,81", "3,00", "14,43"],
            ["2", "L63x63x5x470", "T2", "4", "1,0", "4,81", "4,00", "19,24"],
            ["3", "L63x63x5x470", "T3", "1", "2,0", "4,81", "2,00", "9,62"]]
    out, flags = repair(rows, ANGLES)
    assert out[1:] == rows[1:] and not flags                # a shifted table is left as it is, not "repaired" with the wrong columns


def test_nothing_is_changed_by_numbers_that_do_not_add_up_anywhere():
    rows = [HEAD, ["1", "T1", "L63x63x5x470", "9", "9", "9", "9", "9"], ["2", "T2", "L63x63x5x470", "9", "9", "9", "9", "9"]]
    out, flags = repair(rows, ANGLES)
    assert out[1:] == rows[1:]


def test_a_column_of_words_is_not_treated_as_numbers():
    head = ["STT", "Chủng loại", "Đơn vị", "Số lượng", "Tổng cộng", "Đơn trọng", "Tổng KL", "Ghi chú"]
    rows = [head, ["1", "Tăng đơ", "CÁI", "18", "18", "6,37", "114,66", ""], ["2", "Ma ní", "CÁI", "36", "36", "1,4", "50,40", ""],
            ["3", "Lót cáp", "CÁI", "36", "36", "0,15", "5,40", ""]]
    out, flags = repair(rows, ANGLES)
    assert out[1:] == rows[1:] and not any(c == 2 for _, c in flags)           # no "not a number" flag on the unit column
