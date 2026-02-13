from app.services.pii_policy import sanitize_outbound_text


def test_sanitize_masks_pii() -> None:
    text = "联系人张三，电话13800138000，邮箱foo@example.com，身份证110101199001011234。"
    result = sanitize_outbound_text(text)
    assert result.pricing_blocked is False
    assert "13800138000" not in result.text
    assert "foo@example.com" not in result.text


def test_sanitize_blocks_pricing() -> None:
    text = "投标报价合计为¥100000。"
    result = sanitize_outbound_text(text)
    assert result.pricing_blocked is True
    assert result.text == "BLOCKED_PRICING_CONTENT"
