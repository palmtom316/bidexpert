"""Unit tests for v1.4 Lifecycle Red-Line Control."""
from __future__ import annotations

from datetime import date, timedelta


from app.services.lifecycle_manager import (
    detect_standard_info,
    validate_asset_lifecycle,
)


class TestDetectStandardInfo:
    def test_gb_standard(self):
        text = "本工程依据GB50052-2009《供配电系统设计规范》执行"
        code, year = detect_standard_info(text)
        assert code == "GB50052"
        assert year == 2009

    def test_gbt_standard(self):
        text = "参考标准：GB/T 14549-1993 电能质量"
        code, year = detect_standard_info(text)
        assert code is not None
        assert "GB" in code

    def test_dl_standard(self):
        text = "DL/T5161-2018 电气装置安装工程"
        code, year = detect_standard_info(text)
        assert code is not None
        assert "DL" in code.upper()
        assert year == 2018

    def test_no_standard(self):
        text = "这是一个普通的施工方案，不涉及标准引用"
        code, year = detect_standard_info(text)
        assert code is None
        assert year is None

    def test_multiple_standards_picks_first(self):
        text = "GB50052-2009和DL/T5161-2018是主要参考标准"
        code, year = detect_standard_info(text)
        assert code is not None  # picks the first one found

    def test_standard_without_year(self):
        text = "执行GB50054相关规定"
        code, year = detect_standard_info(text)
        assert code == "GB50054"
        assert year is None

    def test_ieee_standard(self):
        text = "IEEE 80021-2020 standard for power systems"
        code, year = detect_standard_info(text)
        assert code is not None
        assert "IEEE" in code.upper()

    def test_nb_standard(self):
        text = "NB/T 10123-2019 电力储能用锂离子电池"
        code, year = detect_standard_info(text)
        assert code is not None


class TestValidateAssetLifecycle:
    def test_valid_no_dates(self):
        assert validate_asset_lifecycle(expiration_date=None, valid_to=None) is True

    def test_valid_future_expiration(self):
        future = date.today() + timedelta(days=365)
        assert validate_asset_lifecycle(expiration_date=future) is True

    def test_expired_past_date(self):
        past = date.today() - timedelta(days=1)
        assert validate_asset_lifecycle(expiration_date=past) is False

    def test_expired_today_is_valid(self):
        today = date.today()
        # expiration_date == today means not yet expired (expires at end of day)
        assert validate_asset_lifecycle(expiration_date=today) is True

    def test_valid_to_expired(self):
        past = date.today() - timedelta(days=30)
        assert validate_asset_lifecycle(expiration_date=None, valid_to=past) is False

    def test_valid_to_future(self):
        future = date.today() + timedelta(days=30)
        assert validate_asset_lifecycle(expiration_date=None, valid_to=future) is True

    def test_both_expired(self):
        past = date.today() - timedelta(days=1)
        assert validate_asset_lifecycle(expiration_date=past, valid_to=past) is False

    def test_expiration_expired_valid_to_ok(self):
        past = date.today() - timedelta(days=1)
        future = date.today() + timedelta(days=30)
        # If expiration_date is expired, returns False regardless of valid_to
        assert validate_asset_lifecycle(expiration_date=past, valid_to=future) is False
