from services.opportunity_service.schemas import (
    OpportunityScore,
    ScoreOpportunitiesRequest,
    ScoreOpportunitiesResult,
)


class OpportunityService:
    """Scores Polymarket candidates for agent-readable opportunity selection."""

    def score_opportunities(self, request: ScoreOpportunitiesRequest) -> ScoreOpportunitiesResult:
        scored = [self._score_market(market, request) for market in request.markets]
        if request.min_liquidity is not None:
            scored = [item for item in scored if (item.liquidity or 0) >= request.min_liquidity]
        scored.sort(key=lambda item: item.opportunity_score, reverse=True)
        limit = max(1, min(request.max_results, 50))
        selected = scored[:limit]
        return ScoreOpportunitiesResult(goal=request.goal, opportunities=selected, count=len(selected))

    def _score_market(self, market: dict, request: ScoreOpportunitiesRequest) -> OpportunityScore:
        question = str(market.get("question") or "Untitled Polymarket market")
        outcomes = market.get("outcomes") if isinstance(market.get("outcomes"), list) else []
        outcome = str(outcomes[0]) if outcomes else "Yes"
        price = self._safe_float(market.get("best_yes_price"))
        if price is None:
            prices = market.get("outcome_prices") if isinstance(market.get("outcome_prices"), list) else []
            price = self._safe_float(prices[0]) if prices else None
        liquidity = self._safe_float(market.get("liquidity"))
        volume_24hr = self._safe_float(market.get("volume_24hr"))

        score = 30
        reasons: list[str] = []

        if liquidity is None:
            score -= 35
            reasons.append("missing_liquidity")
        elif liquidity <= 0:
            score -= 45
            reasons.append("no_liquidity")
        elif liquidity >= 10000:
            score += 25
            reasons.append("deep_liquidity")
        elif liquidity >= 1000:
            score += 10
            reasons.append("acceptable_liquidity")
        else:
            score -= 15
            reasons.append("thin_liquidity")

        if volume_24hr is None:
            score -= 5
            reasons.append("missing_recent_volume")
        elif volume_24hr >= 5000:
            score += 20
            reasons.append("strong_recent_volume")
        elif volume_24hr >= 1000:
            score += 10
            reasons.append("some_recent_volume")
        else:
            score -= 10
            reasons.append("low_recent_volume")

        if price is None:
            score -= 40
            reasons.append("missing_price")
        elif price <= 0 or price >= 1:
            score -= 50
            reasons.append("non_tradable_price")
        elif request.preferred_price_min <= price <= request.preferred_price_max:
            score += 20
            reasons.append("tradable_price_range")
        elif 0.1 <= price <= 0.9:
            score += 8
            reasons.append("wide_but_tradable_price_range")
        else:
            score -= 15
            reasons.append("extreme_price")

        if request.goal and self._matches_goal(question, str(market.get("event_title") or ""), request.goal):
            score += 8
            reasons.append("goal_keyword_match")

        if market.get("closed") or market.get("active") is False:
            score -= 50
            reasons.append("inactive_or_closed")

        untradable = any(
            reason in reasons
            for reason in ["missing_price", "non_tradable_price", "missing_liquidity", "no_liquidity", "inactive_or_closed"]
        )
        score = max(0, min(100, score))
        if untradable:
            risk_level = "high"
            action = "reject"
        elif score >= 70:
            risk_level = "low"
            action = "paper_trade"
        elif score >= 45:
            risk_level = "medium"
            action = "watch"
        else:
            risk_level = "high"
            action = "reject"

        return OpportunityScore(
            market_id=str(market.get("market_id") or market.get("id") or market.get("condition_id") or "unknown_market"),
            question=question,
            outcome=outcome,
            price=price,
            liquidity=liquidity,
            volume_24hr=volume_24hr,
            opportunity_score=score,
            risk_level=risk_level,
            recommended_action=action,
            reasons=reasons,
            market=market,
        )

    @staticmethod
    def _matches_goal(question: str, event_title: str, goal: str) -> bool:
        haystack = f"{question} {event_title}".lower()
        keywords = [token.strip(".,;:!?()[]{}\"\'").lower() for token in goal.split()]
        keywords = [token for token in keywords if len(token) >= 4]
        return any(token in haystack for token in keywords)

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
