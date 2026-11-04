from src.domain.checks import check_bracing_length, check_chain, check_members
from src.domain.models import Member
from src.domain.weights import total_mass_kg


def test_total_mass_matches_hand_calculation(rows):
    total, skipped = total_mass_kg([Member.from_dict(r) for r in rows])
    assert abs(total - 1117.4) < 1.0
    assert skipped == 0


def test_no_issues_on_real_data(rows):
    assert check_members([Member.from_dict(r) for r in rows]) == []


def test_duplicate_mark_is_error():
    m = Member("ĐOẠN B", "B1", "L", 50, 5, 100, 1)
    assert [i.level for i in check_members([m, m])] == ["error"]


def test_bolt_without_bo_warns():
    m = Member("X", "M1", "M", 16, 5, 50, 1)
    assert check_members([m])[0].level == "warning"


def test_bracing_formula_catches_c16_error():
    assert check_bracing_length("C16", 1494, 889, 0, 0) != []
    assert check_chain("C1", [100, 200], 300) == []
    assert check_chain("C1", [100, 200], 310) != []


def test_from_dict_coerces_model_strings():
    m = Member.from_dict({"section": "B", "mark": "B1", "type": "L", "w": "50", "t": "5,5", "len": "704.0", "qty": "4"})
    assert (m.w, m.t, m.len, m.qty) == (50, 5.5, 704, 4)
    assert Member.from_dict({"section": "B", "type": "M", "w": 16, "t": "Bộ", "len": 50, "qty": 2}).t == "Bộ"


def test_from_dict_rejects_garbage():
    import pytest
    for bad in ({"section": "B", "type": "L", "w": "abc", "len": 1, "qty": 1},
                {"section": "B", "type": "L", "w": 1, "len": 1}):
        with pytest.raises((ValueError, KeyError)):
            Member.from_dict(bad)
