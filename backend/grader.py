"""
Post-draft grading — builds a comprehensive prompt for Gemini
to grade the completed draft team.
"""

import json
from state import DraftState
from config import settings


def build_grade_prompt(state: DraftState) -> str:
    """Build a structured prompt for Gemini to grade the draft."""
    my = state.my_team
    picks = my.players_acquired
    budget_used = my.total_budget - my.budget

    # Compute value analysis for each pick
    pick_analysis = []
    for pick in picks:
        player = state.get_player(pick["name"])
        if player:
            surplus = player.projection.baseline_aav - pick["price"]
            pick_analysis.append({
                "name": pick["name"],
                "position": pick["position"],
                "price": pick["price"],
                "baseline_aav": player.projection.baseline_aav,
                "surplus_value": round(surplus, 1),
                "projected_points": player.projection.projected_points,
                "tier": player.projection.tier,
            })

    total_surplus = sum(p["surplus_value"] for p in pick_analysis)
    total_projected = sum(p["projected_points"] for p in pick_analysis)

    return f"""You are an expert fantasy {settings.sport_name} analyst. Grade this auction draft team.

DRAFT RESULTS:
{json.dumps(pick_analysis, indent=2)}

SUMMARY:
- Total budget: ${my.total_budget}, Spent: ${budget_used}, Remaining: ${my.budget}
- Total surplus value: ${total_surplus:.1f} (positive = got bargains)
- Total projected points: {total_projected:.1f}
- Roster: {json.dumps({slot: occupant for slot, occupant in my.roster.items()})}

LEAGUE CONTEXT:
- {settings.league_size}-team league
- Final inflation: {state.get_inflation_factor():.3f}
- Players in pool: {len(state.players)}

Provide a JSON response with:
{{
  "overall_grade": "A+" to "F",
  "grade_explanation": "1-2 sentences",
  "strengths": ["list of 2-3 strengths"],
  "weaknesses": ["list of 2-3 weaknesses"],
  "best_pick": {{"name": "...", "reasoning": "..."}},
  "worst_pick": {{"name": "...", "reasoning": "..."}},
  "projected_finish": "1st" to "10th",
  "waiver_targets": ["list of 3-5 player names to target on waivers"],
  "position_grades": {{{", ".join(f'"{p}": "B+"' for p in settings.positions)}}}
}}"""
