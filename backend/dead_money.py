"""
Dead Money Alerts — detect overpays and market shifts after player sales.

An overpay is defined as a sale at >30% above the player's FMV at the time of sale.
Market shifts are triggered when inflation changes by >0.5% after a sale.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import PlayerState
    from state import DraftState

OVERPAY_THRESHOLD = 0.30  # 30%


def check_dead_money(
    player: "PlayerState",
    state: "DraftState",
    pre_sale_inflation: float,
) -> Optional[dict]:
    """Check if a player sale qualifies as dead money (overpay).

    Returns an alert dict if overpay > threshold, else None.
    """
    if not player.is_drafted or player.draft_price is None:
        return None

    fmv_at_sale = player.projection.baseline_aav * pre_sale_inflation
    if fmv_at_sale <= 0:
        return None

    overpay_amount = player.draft_price - fmv_at_sale
    overpay_pct = overpay_amount / fmv_at_sale

    if overpay_pct <= OVERPAY_THRESHOLD:
        return None

    return {
        "player_name": player.projection.player_name,
        "position": player.projection.position.value,
        "team": player.drafted_by_team or "Unknown",
        "draft_price": player.draft_price,
        "fmv_at_sale": round(fmv_at_sale, 1),
        "overpay_amount": round(overpay_amount, 1),
        "overpay_pct": round(overpay_pct * 100, 1),
        "new_inflation": round(state.get_inflation_factor(), 4),
        "pre_inflation": round(pre_sale_inflation, 4),
        "inflation_change": round(state.get_inflation_factor() - pre_sale_inflation, 4),
    }


def process_dead_money_alerts(
    newly_drafted: list["PlayerState"],
    state: "DraftState",
    pre_sale_inflation: float,
) -> list[dict]:
    """Check all newly drafted players for overpays.

    Pushes DEAD_MONEY and MARKET_SHIFT events to the ticker.
    Returns list of alert dicts.
    """
    from ticker import TickerBuffer, TickerEvent, TickerEventType
    import time

    ticker = TickerBuffer()
    alerts = []
    now = time.time()

    for player in newly_drafted:
        alert = check_dead_money(player, state, pre_sale_inflation)
        if alert:
            alerts.append(alert)
            ticker.push(TickerEvent(
                event_type=TickerEventType.DEAD_MONEY,
                timestamp=now,
                message=(
                    f"OVERPAY: {alert['team']} paid ${alert['draft_price']} "
                    f"for {alert['player_name']} (FMV ${alert['fmv_at_sale']}, "
                    f"+{alert['overpay_pct']}%)"
                ),
                player_name=alert["player_name"],
                team_name=alert["team"],
                amount=float(alert["draft_price"]),
                details=alert,
            ))

    # Check for market shift (inflation change > 0.5%)
    inflation_change = abs(state.get_inflation_factor() - pre_sale_inflation)
    if inflation_change > 0.005 and newly_drafted:
        direction = "up" if state.get_inflation_factor() > pre_sale_inflation else "down"
        ticker.push(TickerEvent(
            event_type=TickerEventType.MARKET_SHIFT,
            timestamp=now,
            message=(
                f"MARKET SHIFT: Inflation moved {direction} to "
                f"{state.get_inflation_factor():.3f}x "
                f"({'+' if direction == 'up' else '-'}{inflation_change:.3f})"
            ),
            details={
                "pre_inflation": round(pre_sale_inflation, 4),
                "new_inflation": round(state.get_inflation_factor(), 4),
                "change": round(inflation_change, 4),
            },
        ))

    return alerts
