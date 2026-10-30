"""Deterministic document checklist for common life-policy events."""

DOCUMENTS_BY_EVENT = {
    "Maturity payout": ["Policy schedule", "Identity and bank details", "Maturity claim form"],
    "Death benefit claim": ["Policy schedule", "Death certificate", "Claimant identity", "Medical or other records requested by insurer"],
    "Surrender request": ["Policy schedule", "Policyholder identity", "Surrender request form", "Bank details"],
    "Policy loan request": ["Policy schedule", "Policyholder identity", "Loan request form", "Bank details"],
}


def assess_scenario(policy, event, documents_available):
    """Return a prompt to verify requirements; never decide claim eligibility."""
    required = DOCUMENTS_BY_EVENT.get(event, [])
    missing = [name for name in required if name not in documents_available]
    if missing:
        status = "Items to prepare"
        message = "Some commonly requested items are not selected. The insurer may require additional documents."
    else:
        status = "Checklist reviewed"
        message = "The selected items cover this illustrative checklist. Confirm the current requirements with the insurer."
    relevant_terms = {
        "Maturity payout": ("maturity", "premium"),
        "Death benefit claim": ("death", "claims", "exclusion"),
        "Surrender request": ("surrender",),
        "Policy loan request": ("loan", "surrender"),
    }.get(event, ())
    relevant = [clause for clause in policy.get("clauses", []) if any(
        marker in clause["category"].lower() for marker in relevant_terms
    )]
    return {"status": status, "message": message, "missing_documents": missing, "relevant_clauses": relevant}
