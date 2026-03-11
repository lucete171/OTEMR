"""
트렌드 분석 단위 테스트.
BQ 없이 fixture 데이터로 실행 가능.
"""
import pytest
from tests.fixtures.patient_dm_ckd import get_fixture
from analysis.trend import compute_trends


@pytest.fixture
def dm_ckd_record():
    return get_fixture()


@pytest.fixture
def dm_ckd_trends(dm_ckd_record):
    item_ids = list({lab.itemid for lab in dm_ckd_record.labs})
    return compute_trends(dm_ckd_record.labs, item_ids)


class TestCreatinineTrend:
    def test_direction_is_worsening(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert cr.direction == "WORSENING"

    def test_last_value_is_latest(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert cr.last_value == pytest.approx(2.1, abs=0.01)

    def test_ref_flag_is_high(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert cr.ref_flag == "HIGH"

    def test_delta_pct_positive(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert cr.delta_pct is not None
        assert cr.delta_pct > 0

    def test_sparkline_max_10_points(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert len(cr.sparkline) <= 10

    def test_sparkline_sorted_by_time(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        dates = [d for d, _ in cr.sparkline]
        assert dates == sorted(dates)

    def test_slope_is_positive(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        # 6개 포인트 — slope 계산됨
        assert cr.slope is not None
        assert cr.slope > 0


class TestHbA1cGap:
    def test_hba1c_has_data(self, dm_ckd_trends):
        # fixture에서 HbA1c는 175일 전 데이터만 있음
        hba1c = dm_ckd_trends.get(50852)
        assert hba1c is not None
        assert hba1c.has_recent_data  # 180일 이내 데이터는 있음

    def test_missing_item_returns_no_data(self, dm_ckd_record):
        # 존재하지 않는 item_id → has_recent_data=False
        trends = compute_trends(dm_ckd_record.labs, [99999])
        assert 99999 in trends
        assert not trends[99999].has_recent_data


class TestHemoglobinTrend:
    def test_hemoglobin_worsening(self, dm_ckd_trends):
        hgb = dm_ckd_trends[51222]
        assert hgb.direction == "WORSENING"

    def test_hemoglobin_last_value(self, dm_ckd_trends):
        hgb = dm_ckd_trends[51222]
        assert hgb.last_value == pytest.approx(10.7, abs=0.01)


class TestPotassiumTrend:
    def test_potassium_ref_flag_high(self, dm_ckd_trends):
        k = dm_ckd_trends[50971]
        assert k.ref_flag == "HIGH"


class TestSummaryStr:
    def test_summary_str_contains_label(self, dm_ckd_trends):
        cr = dm_ckd_trends[50912]
        assert "Creatinine" in cr.summary_str

    def test_summary_str_no_data(self, dm_ckd_record):
        trends = compute_trends(dm_ckd_record.labs, [99999])
        assert "[데이터 없음]" in trends[99999].summary_str
