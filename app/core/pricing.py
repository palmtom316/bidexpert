from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelPricing:
    input_price_per_m: float  # Price per 1M input tokens
    output_price_per_m: float  # Price per 1M output tokens
    currency: str = "USD"


# Pricing dictionary: model_name -> ModelPricing
# Prices are approximated as of late 2024 / early 2025.
PRICING_MAP: dict[str, ModelPricing] = {
    # OpenAI
    "gpt-4o": ModelPricing(5.00, 15.00),
    "gpt-4o-mini": ModelPricing(0.15, 0.60),
    "o1-preview": ModelPricing(15.00, 60.00),
    "o1-mini": ModelPricing(3.00, 12.00),
    
    # DeepSeek (API pricing is very low, often noted in CNY but mapped to strict USD for consistency if needed)
    # DeepSeek V3: Input 2元/百万, Output 8元/百万 (approx $0.28 / $1.12)
    "deepseek-chat": ModelPricing(0.28, 1.12),
    "deepseek-reasoner": ModelPricing(0.28, 1.12),  # R1 pricing similar to V3 in some contexts, or slightly higher

    # Qwen (Alibaba Cloud Bailian)
    # Qwen-Turbo: 0.002元/千 -> 2元/百万 ($0.28)
    # Qwen-Plus: 0.004元/千 -> 4元/百万 ($0.56)
    # Qwen-Max: 0.02元/千 -> 20元/百万 ($2.80)
    "qwen-turbo": ModelPricing(0.28, 0.28),  # Often distinct in/out, simplified here
    "qwen-plus": ModelPricing(0.56, 1.68),
    "qwen-max": ModelPricing(2.80, 8.40),
    "qwen3": ModelPricing(0.56, 1.68), # Valid alias
    
    # Anthropic
    "claude-3-5-sonnet-20241022": ModelPricing(3.00, 15.00),
    "claude-3-5-haiku-20241022": ModelPricing(1.00, 5.00),
}


def get_estimated_cost(model_name: str, input_tokens: int, output_tokens: int) -> tuple[float, str]:
    """
    Calculate estimated cost for a given model and token usage.
    Returns (cost, currency).
    """
    # Normalize model name for matching (simple containment or exact match)
    key = model_name.lower()
    
    # Direct match
    if key in PRICING_MAP:
        pricing = PRICING_MAP[key]
        cost = (input_tokens / 1_000_000 * pricing.input_price_per_m) + \
               (output_tokens / 1_000_000 * pricing.output_price_per_m)
        return cost, pricing.currency

    # Partial match heuristics
    for p_key, pricing in PRICING_MAP.items():
        if p_key in key:
            cost = (input_tokens / 1_000_000 * pricing.input_price_per_m) + \
                   (output_tokens / 1_000_000 * pricing.output_price_per_m)
            return cost, pricing.currency
            
    # Fallback: Assume GPT-4o-mini rates for unknown models
    fallback = PRICING_MAP["gpt-4o-mini"]
    cost = (input_tokens / 1_000_000 * fallback.input_price_per_m) + \
           (output_tokens / 1_000_000 * fallback.output_price_per_m)
    return cost, fallback.currency
