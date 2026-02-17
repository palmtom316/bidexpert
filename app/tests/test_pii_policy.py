from app.services.pii_policy import sanitize_outbound_text


def _valid_id_card(base17: str) -> str:
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    mapping = "10X98765432"
    checksum = sum(int(digit) * weight for digit, weight in zip(base17, weights, strict=True)) % 11
    return base17 + mapping[checksum]


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


def test_sanitize_masks_only_valid_id_card() -> None:
    valid_id = _valid_id_card("11010119900101123")
    invalid_id = "110101199001011234"
    text = f"身份证A:{valid_id}；身份证B:{invalid_id}。"
    result = sanitize_outbound_text(text, sensitive_strategy="allowlist", allowlist=["身份证B"])
    assert valid_id not in result.text
    assert invalid_id in result.text
