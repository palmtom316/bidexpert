from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.tender.assets.repository import list_personnel_candidates_from_asset_pool


def match_personnel_team(
    db: Session,
    *,
    project_id: uuid.UUID,
    role_requirements: list[dict[str, Any]],
    ownership_roles: list[str] | None = None,
) -> dict[str, Any]:
    normalized_requirements: list[dict[str, Any]] = []
    for item in role_requirements:
        role = str(item.get("role", "")).strip()
        if not role:
            continue
        normalized_requirements.append(
            {
                "role": role,
                "social_security_months": item.get("social_security_months"),
                "no_active_project": bool(item.get("no_active_project", False)),
            }
        )

    if not normalized_requirements:
        return {"matched": True, "team": [], "missing_roles": [], "total_score": 0.0}

    candidates_by_role: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for requirement in normalized_requirements:
        candidates = list_personnel_candidates_from_asset_pool(
            db,
            project_id=project_id,
            ownership_roles=ownership_roles,
            role=requirement["role"],
            no_active_project=requirement["no_active_project"],
            social_security_months=requirement["social_security_months"],
        )
        candidates_by_role.append((requirement, candidates))

    best = _pick_best_team(candidates_by_role)
    required_counter = Counter(item["role"] for item in normalized_requirements)
    matched_counter = Counter(item["role"] for item in best["team"])
    missing_counter = required_counter - matched_counter
    missing_roles: list[str] = []
    for role, count in missing_counter.items():
        missing_roles.extend([role] * count)
    return {
        "matched": len(missing_roles) == 0,
        "team": best["team"],
        "missing_roles": missing_roles,
        "total_score": best["total_score"],
    }


def _pick_best_team(
    candidates_by_role: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> dict[str, Any]:
    best = {"filled_count": -1, "total_score": -1.0, "team": []}

    def dfs(index: int, used_assets: set[uuid.UUID], team: list[dict[str, Any]], score: float) -> None:
        nonlocal best
        if index >= len(candidates_by_role):
            filled_count = len(team)
            if filled_count > best["filled_count"] or (
                filled_count == best["filled_count"] and score > best["total_score"]
            ):
                best = {"filled_count": filled_count, "total_score": score, "team": list(team)}
            return

        requirement, candidates = candidates_by_role[index]
        chosen = False
        for candidate in candidates:
            asset_id = candidate["asset_pool_id"]
            if asset_id in used_assets:
                continue
            chosen = True
            used_assets.add(asset_id)
            candidate_score = float(candidate.get("match_score", 0.0) or 0.0)
            team.append(
                {
                    "role": requirement["role"],
                    "asset_pool_id": asset_id,
                    "asset_name": candidate["asset_name"],
                    "ownership_role": candidate["ownership_role"],
                    "score": candidate_score,
                    "evidence_refs": list(candidate.get("evidence_refs", [])),
                }
            )
            dfs(index + 1, used_assets, team, score + candidate_score)
            team.pop()
            used_assets.remove(asset_id)

        if not chosen:
            dfs(index + 1, used_assets, team, score)

    dfs(0, set(), [], 0.0)
    return best
