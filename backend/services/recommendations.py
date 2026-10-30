"""Hard-filtered, explainable preference scoring."""


def rank_policies(policies, minimum_cover_lakh, maximum_premium, weights, age=None, goal=None, location_records=None):
    """Filter against stated hard constraints, then transparently score preferences.

    Unknown age eligibility is surfaced for review instead of assumed eligible.
    Health and occupation disclosures are contextual only and never exclusion criteria.
    """
    eligible = [
        dict(policy)
        for policy in policies
        if policy.get("sum_assured_lakh", 0) >= minimum_cover_lakh
        and policy.get("premium", float("inf")) <= maximum_premium
        and (age is None or age >= policy.get("minimum_entry_age", age))
        and (age is None or age <= policy.get("maximum_entry_age", age))
    ]
    if not eligible:
        return []

    premiums = [policy["premium"] for policy in eligible]
    covers = [policy["sum_assured_lakh"] for policy in eligible]
    low, high = min(premiums), max(premiums)
    max_cover = max(covers) or 1
    for policy in eligible:
        policy["price_score"] = 100 if low == high else round((high - policy["premium"]) / (high - low) * 100)
        values = {key: policy.get(key, 0) for key in weights}
        if "coverage_score" in values:
            values["coverage_score"] = round(policy["sum_assured_lakh"] / max_cover * 100)
        product_type = policy.get("product_type", "").lower()
        if "benefit_score" in values:
            if goal == "Periodic payouts":
                values["benefit_score"] = 100 if "money-back" in product_type else 35
            elif goal == "Long-term savings and maturity value":
                values["benefit_score"] = 100 if "endowment" in product_type else (65 if "whole-life" in product_type else 40 if "money-back" in product_type else 0)
            elif goal == "Larger life cover":
                values["benefit_score"] = 50
            elif goal == "Protection duration":
                values["benefit_score"] = 100 if policy.get("category") == "Term life" else 35
            else:
                values["benefit_score"] = 50
        if "local_support_score" in values:
            records = location_records or []
            matched = any(
                str(record.get("insurer", "")).casefold() == str(policy.get("insurer", "")).casefold()
                or policy.get("uin") in record.get("product_uins", [])
                or policy.get("name") in record.get("product_names", [])
                for record in records
            )
            values["local_support_score"] = 100 if matched else 0
            policy["local_support_match"] = matched
        policy["age_eligibility_known"] = "minimum_entry_age" in policy or "maximum_entry_age" in policy
        denominator = sum(weights.values()) or 1
        policy["score_breakdown"] = values
        policy["preference_fit"] = round(sum(values[key] * weight for key, weight in weights.items()) / denominator)
    return sorted(eligible, key=lambda item: item["preference_fit"], reverse=True)
