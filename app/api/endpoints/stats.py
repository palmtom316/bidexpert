from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.pricing import get_estimated_cost
from app.db.session import SessionLocal
from app.models.tables import LLMCallLog

router = APIRouter()


class ModelUsageStats(BaseModel):
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    call_count: int
    estimated_cost: float
    currency: str


class UsageStatsResponse(BaseModel):
    items: list[ModelUsageStats]
    total_cost_usd: float


@router.get("/usage", response_model=UsageStatsResponse)
def get_usage_stats():
    """
    Get aggregated token usage and estimated cost by model.
    """
    with SessionLocal() as db:
        # Group by model_name
        stmt = (
            select(
                LLMCallLog.model_name,
                func.sum(LLMCallLog.input_tokens).label("input_sum"),
                func.sum(LLMCallLog.output_tokens).label("output_sum"),
                func.count(LLMCallLog.id).label("call_count"),
            )
            .group_by(LLMCallLog.model_name)
        )
        
        rows = db.execute(stmt).all()
        
        items: list[ModelUsageStats] = []
        total_usd = 0.0

        for row in rows:
            model_name = row.model_name
            input_tokens = int(row.input_sum or 0)
            output_tokens = int(row.output_sum or 0)
            call_count = int(row.call_count or 0)
            
            cost, currency = get_estimated_cost(model_name, input_tokens, output_tokens)
            
            # Simple normalization for total aggregation (assuming roughly 1 USD for all for simplicity in header)
            # In a real app, might need currency conversion. Here we just sum up.
            if currency == "USD":
                total_usd += cost
            elif currency == "CNY": # If we added CNY support
                total_usd += cost / 7.2  # Approx exchange rate
            
            items.append(ModelUsageStats(
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                call_count=call_count,
                estimated_cost=round(cost, 4),
                currency=currency
            ))
            
        return UsageStatsResponse(items=items, total_cost_usd=round(total_usd, 4))
