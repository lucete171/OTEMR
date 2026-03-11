"""
Change flag 감지 단위 테스트.
"""
import pytest
from tests.fixtures.patient_dm_ckd import get_fixture
from analysis.trend import compute_trends
from analysis.flags import detect_flags


@pytest.fixture
def flags():
    record = get_fixture()
    item_ids = list({lab.itemid for lab in record.labs})
    trends = compute_trends(record.labs, item_ids)
    return detect_flags(trends)


def test_creatinine_flag_detected(flags):
    cr_flags = [f for f in flags if f.item_id == 50912]
    assert len(cr_flags) > 0


def test_creatinine_flag_severity(flags):
    cr_flags = [f for f in flags if f.item_id == 50912]
    severities = {f.severity for f in cr_flags}
    # Cr 2.1 + 큰 delta → HIGH 또는 MEDIUM
    assert severities & {"HIGH", "MEDIUM"}


def test_high_severity_comes_first(flags):
    if len(flags) < 2:
        pytest.skip("Not enough flags to test ordering")
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for i in range(len(flags) - 1):
        assert order.get(flags[i].severity, 3) <= order.get(flags[i + 1].severity, 3)


def test_flag_has_message(flags):
    for f in flags:
        assert f.message
        assert len(f.message) > 0


def test_flag_current_value_set(flags):
    for f in flags:
        assert f.current_value is not None
