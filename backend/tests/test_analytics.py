import pytest

from app.services import analytics_service as a


def test_attendance_percentage():
    assert a.attendance_percentage(32, 0, 0, 41) == round(32 / 41 * 100, 2)
    assert a.attendance_percentage(0, 0, 0, 0) == 0.0
    assert a.attendance_percentage(10, 2, 1, 20) == round(13 / 20 * 100, 2)


@pytest.mark.parametrize(
    "attended,total,required_pct,expected",
    [
        (32, 41, 75.0, 1),  # 32/42 = 76.19% still >=75, 32/43=74.4% not enough -> can miss 1
        (40, 40, 75.0, 13),  # 40/(40+k)>=0.75 -> k<=13.33 -> 13
        (10, 10, 50.0, 10),
    ],
)
def test_classes_can_miss(attended, total, required_pct, expected):
    result = a.classes_can_miss(attended, total, required_pct)
    assert result == expected
    # Verify the invariant directly: attended/(total+result) must still meet the bar,
    # and one more miss would break it.
    assert attended / (total + result) * 100 >= required_pct - 1e-9
    assert attended / (total + result + 1) * 100 < required_pct + 1e-9


def test_classes_can_miss_never_negative():
    assert a.classes_can_miss(1, 20, 75.0) == 0


def test_classes_needed_to_recover_already_met():
    assert a.classes_needed_to_recover(35, 40, 75.0) == 0


def test_classes_needed_to_recover_below_threshold():
    # 20/40 = 50%, need k s.t. (20+k)/(40+k) >= 0.75
    k = a.classes_needed_to_recover(20, 40, 75.0)
    assert (20 + k) / (40 + k) * 100 >= 75.0 - 1e-9
    assert (20 + k - 1) / (40 + k - 1) * 100 < 75.0 + 1e-9 if k > 0 else True


def test_classes_needed_to_recover_zero_total():
    assert a.classes_needed_to_recover(0, 0, 75.0) == 0


def test_projected_after_attending_n():
    assert a.projected_after_attending_n(30, 40, 5) == round(35 / 45 * 100, 2)


def test_projected_after_missing_n():
    assert a.projected_after_missing_n(30, 40, 5) == round(30 / 45 * 100, 2)


def test_projected_functions_zero_denominator_safe():
    assert a.projected_after_attending_n(0, 0, 0) == 0.0
    assert a.projected_after_missing_n(0, 0, 0) == 0.0
