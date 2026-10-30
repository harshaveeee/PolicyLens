# PolicyLens

PolicyLens is a Streamlit prototype for comparing term and non-term life insurance products, explaining selected policy clauses, preparing for common policy requests, and finding sourced insurer support by location. The current scope includes term, endowment, whole-life and money-back products. Health, motor and other insurance categories are future avenues.

## Run locally

```bash
python -m venv .venv
```

Activate the environment, then install and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Current data status

- `data/market_reference.json` contains Policybazaar product listings, insurer figures and investment-plan values transcribed from the user-provided numerical extraction document. It records the source URL, access date, reporting context and limitations. The dynamic source has not been independently verified.
- `data/policies.json` contains illustrative demonstration records for the clause-explanation and claim-readiness workflows. These are not current insurer offers, sourced policy clauses or premium quotations.
- `data/branches.json` is empty until verified insurer branch/adviser records are provided.
- `data/occupations.json` contains a descriptive occupation/exposure taxonomy. It is not an underwriting, medical, actuarial or pricing model.
- Applicant health details are optional, require explicit on-screen consent, are not sent to an AI service, and are not used to reject or score a policy.

Real product documents must be checked against the official source and entered with product/UIN, version, effective date, source URL, page and extraction confidence. Keep extracted wording/facts separate from plain-language explanations.
Verified branch/adviser records should include a name, city or PIN, latitude/longitude, official source URL and last-verified date before they are used in the location map.
For location-aware ranking, branch records should also identify the insurer and associated product UINs or product names. A matching PIN enables a transparent local-support preference factor; missing directory data does not affect ranking.
Demonstration premiums are not age-based quotations. Real premiums and underwriting decisions must come from the insurer.

## Main workflows

- Choose term life, non-term life or all life products; compare benefits and source-linked clauses.
- Filter example policies by age range, requested sum assured and premium budget; rank by transparent goal preferences.
- Review common maturity, death-benefit, surrender and policy-loan document prompts.
- Match a PIN/city to verified insurer branches/advisers when sourced records are loaded.
- View descriptive occupation context without underwriting or price conclusions.
- Extract text page by page from uploaded text-based PDFs. Uploaded documents currently receive rule-based categories and review prompts, not generated explanations.

## Project structure

- `app.py` starts the Streamlit frontend.
- `frontend/` contains the user interface.
- `backend/repository.py` reads structured reference records.
- `backend/services/` contains document, recommendation, claim-preparation, geography and occupation logic.
- `data/` contains product, branch and occupation records.

PolicyLens provides decision support and education. It is not financial advice, an underwriting assessment or an insurer decision. Confirm contract terms, current values and all disclosures with the insurer or a qualified adviser.
