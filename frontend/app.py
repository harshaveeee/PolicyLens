"""Streamlit screens for the PolicyLens life-insurance comparison prototype."""

import streamlit as st
import pydeck as pdk

from backend.repository import get_branches, get_market_reference, get_occupations, get_policies
from backend.services.claim_readiness import DOCUMENTS_BY_EVENT, assess_scenario
from backend.services.documents import classify_page_text, extract_pdf_pages, make_review_note
from backend.services.geography import find_locations, nearby_locations, location_centroid
from backend.services.occupations import get_profile
from backend.services.recommendations import rank_policies


_GEO_COMPONENT = st.components.v2.component(
    "policylens_device_location",
    html='<button type="button" data-geolocation-button>Use my current location</button><span data-geolocation-status style="margin-left:.6rem"></span>',
    js="""
    export default function(component) {
      const { setStateValue, parentElement } = component;
      const button = parentElement.querySelector('[data-geolocation-button]');
      const status = parentElement.querySelector('[data-geolocation-status]');
      button.onclick = () => {
        if (!navigator.geolocation) { status.textContent = 'Location is unavailable in this browser.'; return; }
        status.textContent = 'Requesting location permission…';
        navigator.geolocation.getCurrentPosition(
          (position) => {
            setStateValue('coordinates', {lat: position.coords.latitude, lon: position.coords.longitude});
            setStateValue('error', '');
            status.textContent = 'Location is active for this session.';
          },
          (error) => { setStateValue('error', error.message); status.textContent = 'Location was not shared. Enter a PIN or city instead.'; },
          {enableHighAccuracy: false, timeout: 10000, maximumAge: 300000}
        );
      };
    }
    """,
)


def _styles():
    st.markdown("""
    <style>
    :root { --ink:#142b3b; --muted:#678091; --line:#e4ebef; --teal:#087f83; --mint:#e8f6f3; --paper:#f6f9fa; }
    html, body, [class*="css"] { font-family:Arial,sans-serif; }
    .stApp { background:var(--paper); color:var(--ink); }
    [data-testid="stSidebar"] { background:#102b3a; }
    [data-testid="stSidebar"] * { color:#e5f0f2!important; }
    .brand {font-weight:800;letter-spacing:-.04em;font-size:1.55rem;color:#fff;margin:0;}
    .brand span {color:#52d3c1;}
    .eyebrow {color:#078487;font-weight:700;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;}
    .hero {padding:1.8rem 2rem;border-radius:20px;background:linear-gradient(110deg,#102d3b 0%,#174c57 65%,#187c7a 100%);color:#fff;margin:.4rem 0 1.2rem;}
    .hero h1 {font-size:2.2rem;letter-spacing:-.04em;color:#fff;margin:.3rem 0 .45rem;}
    .hero p {color:#cce1e5;margin:0;max-width:780px;}
    .panel {background:#fff;border:1px solid var(--line);border-radius:15px;padding:1rem 1.1rem;box-shadow:0 3px 12px #102b3a08;}
    .source {border-left:3px solid #56b8ad;background:#f2faf8;padding:.7rem .85rem;border-radius:0 9px 9px 0;color:#244253;font-size:.9rem;}
    .subtle {color:#6e8492;font-size:.82rem;}
    div[data-testid="stMetric"] {background:#fff;border:1px solid var(--line);padding:.9rem 1rem;border-radius:14px;}
    .stButton>button[kind="primary"] {background:#087f83;border-color:#087f83;border-radius:10px;}
    </style>
    """, unsafe_allow_html=True)


def _render_clause(policy, clause):
    with st.expander(f"{clause['category']} · Page {clause['page']}"):
        st.markdown("**In plain language**")
        st.write(clause["explanation"])
        st.caption(f"Source reference: {policy['source']} · {policy['version']} · Page {clause['page']}")
        if clause.get("extraction_confidence") is not None:
            st.caption(f"Text extraction confidence: {clause['extraction_confidence']:.0%}")
        with st.expander("View reference wording"):
            st.write(clause["text"])
        st.caption("This bundled wording is illustrative, not a quotation from an insurer. Confirm exact wording in the official document.")


def _policy_upload():
    with st.expander("Review a policy PDF"):
        uploaded = st.file_uploader("Upload a life-policy wording PDF", type=["pdf"], key="life_policy_pdf")
        if uploaded:
            try:
                pages = extract_pdf_pages(uploaded.getvalue())
                selectable = [item for item in pages if item["has_text"]]
                if not selectable:
                    st.warning("No selectable text was found. The PDF may be scanned or image-only.")
                else:
                    page = st.selectbox("Extracted page", selectable, format_func=lambda item: f"Page {item['page']}")
                    category = classify_page_text(page["text"])
                    left, right = st.columns(2)
                    with left:
                        st.markdown(f"**Extracted wording · {category}**")
                        st.text_area("Policy text", page["text"], height=230, label_visibility="collapsed")
                    with right:
                        st.markdown("**Review prompt**")
                        st.info(make_review_note(category))
                        st.caption("Uploaded documents are extracted for review; this build does not create AI interpretations of new PDFs.")
            except RuntimeError as error:
                st.error(str(error))
            except Exception:
                st.error("This PDF could not be read. Try a text-based policy PDF.")


def _market_reference(reference, product_focus):
    st.markdown("### Market reference data")
    st.caption(f"Source: [{reference['source_title']}]({reference['source_url']}) · Accessed {reference['accessed_date']}")
    facts = reference["market_facts"]
    st.write(f"The source lists {facts['insurers_in_comparison']} insurer snapshots, {facts['term_products_listed']} term products and {facts['investment_plans_listed']} investment plans.")
    st.caption(f"The page advertises {facts['advertised_term_cover']} cover at {facts['advertised_monthly_premium']}/month. {facts['advertised_premium_qualification']}")
    with st.expander("Insurer snapshot", expanded=True):
        st.caption(reference["insurer_comparison"]["period_label"] + f" · Premium unit: {reference['insurer_comparison']['premium_unit']}")
        for record in reference["insurer_comparison"]["records"]:
            solvency = record["solvency_ratio_table"]
            if record.get("solvency_ratio_text"):
                solvency += f" (insurer paragraph: {record['solvency_ratio_text']})"
            st.markdown(f"**{record['insurer']}** · Annualized premium ₹{record['annualized_premium_crore']:,.2f} crore · Claim ratio: {record['claim_settlement_ratio']} · Solvency: {solvency}")
            st.caption(record["context"])
    if product_focus in ("All life policies", "Term life"):
        with st.expander("Term products and sum-assured ranges"):
            for record in reference["term_products"]:
                st.markdown(f"- **{record['product']}** · {record['insurer']} · {record['sum_assured_range']}")
    if product_focus in ("All life policies", "Non-term life"):
        with st.expander("Investment-plan figures shown by the source"):
            st.caption("The source provides displayed 5-year and 10-year return figures, but not enough methodology to assess comparability or treat them as guaranteed or forward returns.")
            for record in reference["investment_plans"]:
                st.markdown(f"- **{record['product']}** · {record['insurer']} · 5-year: {record['five_year_return']} · 10-year: {record['ten_year_return']}")
    for limitation in reference["limitations"]:
        st.caption(f"• {limitation}")


def _comparison(policies, branches, occupations, pin, market_reference, product_focus):
    st.markdown('<div class="eyebrow">Life policy explorer</div>', unsafe_allow_html=True)
    policy_category = policies[0]["category"] if policies and len({item["category"] for item in policies}) == 1 else "life"
    st.title(f"Compare {policy_category.lower()} policies" if policy_category != "life" else "Compare life policies")
    st.write("Review source-listed products and insurer figures, then compare policy details where wording is available. Choose term life or non-term life in the sidebar.")
    _market_reference(market_reference, product_focus)
    st.markdown("### Policy clause examples")
    st.caption("The clause workflows below remain illustrative until official policy wording is added.")
    _policy_upload()

    names = [item["name"] for item in policies]
    chosen = st.multiselect("Policies to compare", names, default=names[:2])
    selected = [item for item in policies if item["name"] in chosen]
    if selected:
        labels = [("Product", "product_type"), ("Insurer", "insurer"), ("Product UIN", "uin"),
                  ("Version / effective date", "version_date"), ("Official source URL", "source_url"),
                  ("Illustrative sum assured", "sum_assured"),
                  ("Annual premium example", "premium"), ("Premium-paying term", "premium_term_years"),
                  ("Policy term", "policy_term_years"), ("Maturity / payout structure", "maturity"),
                  ("Death benefit", "death_benefit"), ("Surrender", "surrender")]
        cols = st.columns(len(selected) + 1)
        cols[0].markdown("**Policy detail**")
        for col, policy in zip(cols[1:], selected):
            col.markdown(f"**{policy['name']}**")
            col.caption(policy["insurer"])
        for label, key in labels:
            cells = st.columns(len(selected) + 1)
            cells[0].markdown(f"**{label}**")
            for cell, policy in zip(cells[1:], selected):
                if key == "premium":
                    value = f"₹{policy[key]:,}/year"
                elif key == "version_date":
                    value = f"{policy.get('version', 'Not listed')} · {policy.get('effective_date', 'Not listed')}"
                elif key == "source_url":
                    value = policy.get("source_url") or "Not supplied in example"
                else:
                    value = policy.get(key, "Not listed")
                cell.write(value)
        st.markdown("### Clause explanations")
        policy_name = st.selectbox("View explanations from", [item["name"] for item in selected])
        policy = next(item for item in selected if item["name"] == policy_name)
        for clause in policy["clauses"]:
            _render_clause(policy, clause)

    st.divider()
    st.markdown("### Find a closer match")
    st.write("The ranking applies stated budget and age limits, then explains how plan features match the selected goal. It does not assess insurability or calculate an insurer quote.")
    first, second, third = st.columns(3)
    with first:
        age = st.number_input("Applicant age", min_value=18, max_value=100, value=30, step=1, key="recommend_age")
    with second:
        min_cover = st.number_input("Minimum sum assured (₹ lakh)", min_value=1.0, max_value=100.0, value=5.0, step=1.0)
    with third:
        max_budget = st.number_input("Maximum annual premium (₹)", min_value=1000, max_value=1000000, value=50000, step=1000)
    goals = ["Larger life cover", "Lower annual premium"]
    if any(item["category"] == "Non-term life" for item in policies):
        goals.extend(["Long-term savings and maturity value", "Periodic payouts"])
    if any(item["category"] == "Term life" for item in policies):
        goals.append("Protection duration")
    goal = st.selectbox("Main goal", goals)
    occupation = st.selectbox("Occupation", list(occupations), key="recommend_occupation")
    use_health_context = st.checkbox("I consent to using my health disclosures as on-screen review context")
    health_context = []
    if use_health_context:
        health_context = st.multiselect("Relevant ongoing or recurring health disclosures", [
            "Chronic condition", "Recurring condition or treatment", "Ongoing medication", "Recent or planned investigation", "Prefer to discuss directly with insurer"
        ])
        st.caption("These details stay in this browser session and are not sent to an AI service or used to reject/rank a policy. Disclose relevant information accurately to the insurer.")
    weights = {
        "coverage_score": 5 if goal == "Larger life cover" else 2,
        "price_score": 5 if goal == "Lower annual premium" else 2,
        "benefit_score": 5 if goal in ("Periodic payouts", "Long-term savings and maturity value", "Protection duration") else 2,
    }
    branch_matches, _ = find_locations(branches, pin)
    if branch_matches:
        weights["local_support_score"] = 3
    # Health/occupation are retained only as non-scoring prompts for policy disclosure.
    ranked = rank_policies(policies, min_cover, max_budget, weights, age=age, goal=goal, location_records=branch_matches)
    if not ranked:
        st.warning("No available example meets both the age range and the stated budget/cover limits.")
    for position, policy in enumerate(ranked, start=1):
        with st.container(border=True):
            left, middle, right = st.columns([4, 1, 3])
            left.markdown(f"**{position}. {policy['name']}**")
            left.caption(f"{policy['product_type']} · ₹{policy['premium']:,}/year illustrative premium")
            middle.metric("Preference fit", f"{policy['preference_fit']}/100")
            active = [f"{key.replace('_score', '')} {value} × {weights[key]}" for key, value in policy["score_breakdown"].items()]
            right.caption("Weighted factors (score × weight) · " + " · ".join(active))
            right.caption(f"Premium-paying term: {policy['premium_term_years']} years · Policy term: {policy['policy_term_years']} years")
    if ranked:
        st.caption("Age is checked against the available entry-age fields. Health disclosures and occupation are not scored; review the insurer's underwriting and disclosure requirements directly.")
    st.caption(f"Location input: {pin}. Verified adviser/branch matches are included only where sourced data is available.")
    if health_context:
        st.info("Before applying, check the insurer's health questions and disclose relevant history fully. No policy eligibility conclusion is made here.")
    profile = get_profile(occupations, occupation)
    st.caption(f"Occupation context: {profile['class']} · {profile['label']} (descriptive only; not an underwriting or premium assessment).")
    st.caption("All bundled product facts and clause examples are illustrative, not insurer offers. Confirm current terms and premiums with the insurer.")
    st.caption("Premium examples are not age-based quotations. Official premiums may depend on the insurer's quote and underwriting process.")


def _claim_readiness(policies):
    st.markdown('<div class="eyebrow">Policy event checklist</div>', unsafe_allow_html=True)
    st.title("Prepare for a life-policy request")
    st.write("Review common documents for a maturity payout, death benefit, surrender or policy-loan request.")
    policy = st.selectbox("Policy example", policies, format_func=lambda item: item["name"])
    events = list(DOCUMENTS_BY_EVENT)
    if policy["category"] == "Term life":
        events = ["Death benefit claim"]
    event = st.selectbox("Request type", events)
    documents = st.multiselect("Documents currently available", DOCUMENTS_BY_EVENT[event])
    consent = st.checkbox("I consent to using these selections for this on-screen checklist.")
    if st.button("Review checklist", type="primary"):
        if not consent:
            st.warning("Confirm consent to continue.")
            return
        result = assess_scenario(policy, event, documents)
        st.markdown("### Preparation checklist")
        st.info(f"**{result['status']}:** {result['message']}")
        for item in DOCUMENTS_BY_EVENT[event]:
            st.markdown(("☑ " if item in documents else "☐ ") + item)
        if result["relevant_clauses"]:
            st.markdown("**Related policy terms**")
            for clause in result["relevant_clauses"]:
                _render_clause(policy, clause)
        st.caption("This is a general document prompt, not a claim decision. The insurer sets the official requirements and decides the request.")


def _location_and_occupation(branches, occupations, pin):
    st.markdown('<div class="eyebrow">Location and applicant context</div>', unsafe_allow_html=True)
    st.title("Find local insurer support")
    st.write("Use a PIN code or city to view verified insurer branches or advisers when an official source is available.")
    if not branches:
        st.info("No verified branch or adviser directory is currently loaded. Location-based matching will appear when sourced records are added.")
    else:
        search_from = st.radio("Search from", ["PIN or city", "Current device location"], horizontal=True)
        coords = None
        search_records = branches
        if search_from == "Current device location":
            location_state = _GEO_COMPONENT(
                key="device_location",
                default={"coordinates": None, "error": ""},
                on_coordinates_change=lambda: None,
                on_error_change=lambda: None,
            )
            if location_state.coordinates:
                coords = (location_state.coordinates["lat"], location_state.coordinates["lon"])
                st.caption("Location is used in this session only. The map does not load third-party basemap tiles.")
            else:
                st.caption("Share location in the browser prompt, or select PIN/city. Exact coordinates are not shown.")
        else:
            local, _ = find_locations(branches, pin)
            search_records = local
            coords = location_centroid(branches, pin)
            if pin:
                st.caption("The PIN/city map centre is approximate and based on directory records.")
        if coords:
            radius_km = st.slider("Search radius (km)", 5, 50, 20, 5)
            nearby = nearby_locations(search_records, coords[0], coords[1], radius_km)
            if nearby:
                radius = [{"lat": coords[0], "lon": coords[1], "radius_m": radius_km * 1000}]
                st.pydeck_chart(pdk.Deck(
                    layers=[
                        pdk.Layer("ScatterplotLayer", data=radius, get_position="[lon, lat]", get_radius="radius_m", radius_units="meters",
                                  stroked=True, filled=True, get_fill_color=[8, 127, 131, 28], get_line_color=[8, 127, 131, 180], line_width_min_pixels=2),
                        pdk.Layer("ScatterplotLayer", data=nearby, get_position="[lon, lat]", get_radius=160,
                                  get_fill_color=[236, 143, 48, 220], get_line_color=[255, 255, 255], line_width_min_pixels=1,
                                  pickable=True),
                    ],
                    initial_view_state=pdk.ViewState(latitude=coords[0], longitude=coords[1], zoom=10, pitch=0),
                    map_provider=None,
                    tooltip={"text": "{name}\n{city} · {verified}\n{distance_km} km (straight-line estimate)"},
                    height=420,
                ))
                for branch in nearby:
                    st.markdown(f"**{branch['name']}** · {branch['city']} · {branch['distance_km']} km estimated")
                    st.caption(f"Last verified: {branch['verified']} · Source: {branch['source']}")
    st.markdown("### Occupation context")
    occupation = st.selectbox("Occupation", list(occupations), key="location_occupation")
    profile = get_profile(occupations, occupation)
    st.markdown(f"**{profile['class']} · {profile['label']}**")
    st.write("Descriptive workplace context only. Classification does not estimate underwriting outcome, premium or eligibility.")
    st.caption("Share accurate occupation and health details with the insurer in its application process.")


def main():
    st.set_page_config(page_title="PolicyLens", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
    _styles()
    policies, branches, occupations = get_policies(), get_branches(), get_occupations()
    market_reference = get_market_reference()
    with st.sidebar:
        st.markdown('<p class="brand">Policy<span>Lens</span></p>', unsafe_allow_html=True)
        st.caption("Life insurance, made clearer")
        st.divider()
        page = st.radio("Workspace", ["Overview", "Policy comparison", "Claim readiness", "Location & occupation"], label_visibility="collapsed", key="page_nav")
        product_focus = st.selectbox("Life policy type", ["All life policies", "Term life", "Non-term life"], key="product_focus")
        st.divider()
        st.markdown("**Your profile**")
        pin = st.text_input("PIN code or city", value="", key="pin")
        st.caption("Used only for sourced branch/adviser matching.")
        st.divider()
        st.caption("Policy wording and insurer confirmation determine benefits and claim outcomes.")

    visible_policies = policies if product_focus == "All life policies" else [item for item in policies if item["category"] == product_focus]
    if page == "Overview":
        st.markdown('<div class="hero"><div class="eyebrow" style="color:#7ee2d1">Life policy clarity, in context</div><h1>See what a policy promises<br>and what to verify.</h1><p>Compare term and non-term life products, understand key conditions and prepare better questions for an insurer.</p></div>', unsafe_allow_html=True)
        cols = st.columns(3)
        for col, title, value, detail in zip(cols, ["Life products", "Policy clauses", "Work profiles"],
                                             [len(visible_policies), sum(len(item["clauses"]) for item in visible_policies), len(occupations)],
                                             ["illustrative examples", "with page references", "descriptive context"]):
            col.metric(title, value, detail)
        st.markdown("### Start with a question")
        a, b, c = st.columns(3)
        for col, eyebrow, title, body in [
            (a, "01 · Understand", "What does this term mean?", "Review a plain-language explanation with a page reference."),
            (b, "02 · Compare", "Which plan matches my priorities?", "Compare benefit structure, term and premium examples."),
            (c, "03 · Prepare", "What should I verify?", "Review common documents for a policy request.")]:
            with col:
                st.markdown(f'<div class="panel"><span class="eyebrow">{eyebrow}</span><h3>{title}</h3><p class="subtle">{body}</p></div>', unsafe_allow_html=True)
        st.markdown("### Evidence and context")
        st.info("Policy facts and explanations are kept distinct. Open the source wording when you need to check context.")
        st.markdown("### Published market reference")
        st.write(f"The comparison includes sourced listings for {market_reference['market_facts']['term_products_listed']} term products and {market_reference['market_facts']['investment_plans_listed']} investment plans from Policybazaar.")
        st.caption("These reference listings do not include full policy wordings or comparable premiums. Clause examples remain illustrative. Confirm current details with each insurer.")
    elif page == "Policy comparison":
        _comparison(visible_policies, branches, occupations, pin, market_reference, product_focus)
    elif page == "Claim readiness":
        _claim_readiness(visible_policies)
    else:
        _location_and_occupation(branches, occupations, pin)
    st.markdown("<br><hr><span class='subtle'>PolicyLens · Clear evidence. Better questions. More informed choices.</span>", unsafe_allow_html=True)
