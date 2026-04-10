"""
Change flag 감지 단위 테스트.
"""
import pytest
from tests.fixtures.patient_dm_ckd import get_fixture
from analysis.trend import compute_trends
from analysis.flags import detect_flags, ChangeFlag


@pytest.fixture
def flags():
    record = get_fixture()
    item_ids = list({lab.itemid for lab in record.labs})
    trends = compute_trends(record.labs, item_ids)
    return detect_flags(trends)


# ── 기존 테스트 (유지) ─────────────────────────────────────

def test_creatinine_flag_detected(flags):
    cr_flags = [f for f in flags if f.item_id == 50912]
    assert len(cr_flags) > 0


def test_creatinine_flag_severity(flags):
    cr_flags = [f for f in flags if f.item_id == 50912]
    severities = {f.severity for f in cr_flags}
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


# ── 레이어링 관련 신규 테스트 ──────────────────────────────

def test_all_flags_have_visibility(flags):
    """모든 플래그에 visibility 필드가 있어야 함."""
    valid = {"ALWAYS", "ON_ALERT", "ON_DEMAND"}
    for f in flags:
        assert f.visibility in valid, (
            f"{f.label}: visibility='{f.visibility}' 가 유효하지 않음"
        )


def test_all_flags_have_trigger(flags):
    """모든 플래그에 trigger 필드가 있어야 함."""
    valid = {"THRESHOLD", "TREND", "CONTEXT"}
    for f in flags:
        assert f.trigger in valid, (
            f"{f.label}: trigger='{f.trigger}' 가 유효하지 않음"
        )


def test_creatinine_high_is_layer1(flags):
    """
    Cr 2.1 (abs_high=3.0 미만) → abs 임계값은 안 넘지만
    ref_flag HIGH면 ALWAYS여야 함.
    fixture의 Cr값에 따라 ALWAYS or ON_ALERT.
    어떤 경우든 ON_DEMAND는 아니어야 함.
    """
    cr_flags = [f for f in flags if f.item_id == 50912]
    for f in cr_flags:
        assert f.visibility != "ON_DEMAND", (
            f"Creatinine HIGH/MEDIUM flag가 Layer3(ON_DEMAND)로 분류됨"
        )


def test_threshold_trigger_is_always(flags):
    """THRESHOLD trigger는 반드시 ALWAYS visibility여야 함."""
    for f in flags:
        if f.trigger == "THRESHOLD":
            assert f.visibility == "ALWAYS", (
                f"{f.label}: THRESHOLD인데 visibility={f.visibility}"
            )


def test_trend_alert_has_message(flags):
    """Layer 2 (ON_ALERT) 플래그는 trend_message가 있어야 함."""
    layer2 = [f for f in flags if f.visibility == "ON_ALERT"]
    for f in layer2:
        assert f.trend_message, (
            f"{f.label}: ON_ALERT인데 trend_message가 비어있음"
        )


def test_layer1_flags_exist_for_dm_ckd_fixture(flags):
    """
    DM+CKD fixture는 Cr 상승이 있으므로
    Layer 1 (ALWAYS) 플래그가 최소 1개 이상이어야 함.
    """
    layer1 = [f for f in flags if f.visibility == "ALWAYS"]
    assert len(layer1) >= 1, "DM+CKD 환자에서 Layer1 플래그가 없음"


def test_no_duplicate_item_ids(flags):
    """같은 item_id가 중복으로 플래그되면 안 됨."""
    item_ids = [f.item_id for f in flags]
    assert len(item_ids) == len(set(item_ids)), (
        f"중복 item_id 발견: {[i for i in item_ids if item_ids.count(i) > 1]}"
    )