"""Streamlit screens for the PolicyLens life-insurance comparison prototype."""

import streamlit as st
import pydeck as pdk
import pandas as pd
import os
import hashlib

from backend.repository import get_branches, get_market_reference, get_occupations, get_policies
from backend.services.claim_readiness import DOCUMENTS_BY_EVENT, assess_scenario
from backend.services.documents import classify_page_text, extract_pdf_pages, make_review_note, summarize_policy_text
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
                    facts_tab, summary_tab = st.tabs(["Extracted facts", "AI summary"])
                    with facts_tab:
                        st.caption(f"Source text · {category} · Page {page['page']}")
                        st.text_area("Extracted source wording", page["text"], height=240, label_visibility="collapsed")
                        st.caption("This panel contains text extracted from the uploaded page. Verify it against the original PDF.")
                    with summary_tab:
                        st.markdown("**AI plain-language summary**")
                        api_key = os.environ.get("OPENAI_API_KEY", "")
                        model = os.environ.get("OPENAI_MODEL", "")
                        try:
                            api_key = api_key or st.secrets.get("OPENAI_API_KEY", "")
                            model = model or st.secrets.get("OPENAI_MODEL", "")
                        except Exception:
                            pass
                        configured = bool(api_key and model)
                        if not configured:
                            st.info("AI summaries are unavailable until OPENAI_API_KEY and OPENAI_MODEL are configured in the app secrets.")
                        st.caption("When you request a summary, only the selected page’s extracted text is sent to OpenAI. It is not stored as policy evidence and may omit details; verify every point in the original wording.")
                        consent = st.checkbox("I consent to sending this page’s extracted text to OpenAI for a summary.", key="ai_summary_consent")
                        summary_key = "uploaded_summary_" + hashlib.sha256(f"{uploaded.name}:{page['page']}:{page['text']}".encode("utf-8")).hexdigest()
                        if st.button("Generate AI summary", type="primary", disabled=not (configured and consent), key="generate_policy_summary"):
                            with st.spinner("Summarizing the selected page…"):
                                try:
                                    st.session_state[summary_key] = summarize_policy_text(page["text"], api_key, model)
                                except RuntimeError as error:
                                    st.error(str(error))
                        if summary_key in st.session_state:
                            st.write(st.session_state[summary_key])
                        st.caption(make_review_note(category))
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


def _comparison(policies, market_reference, product_focus):
    st.markdown('<div class="eyebrow">Life policy explorer</div>', unsafe_allow_html=True)
    policy_category = policies[0]["category"] if policies and len({item["category"] for item in policies}) == 1 else "life"
    st.title(f"Compare {policy_category.lower()} policies" if policy_category != "life" else "Compare life policies")
    st.caption("Choose products to compare. Demonstration policy values are illustrative; source-listed market figures are shown separately.")
    _market_reference(market_reference, product_focus)
    st.markdown("### Compare product examples")
    names = [item["name"] for item in policies]
    chosen = st.multiselect("Policies to compare", names, default=names[:2])
    selected = [item for item in policies if item["name"] in chosen]
    if selected:
        chart_col, premium_col = st.columns(2)
        with chart_col:
            st.markdown("**Illustrative sum assured**")
            st.bar_chart(pd.DataFrame({"₹ lakh": {item["name"]: item["sum_assured_lakh"] for item in selected}}), horizontal=True)
        with premium_col:
            st.markdown("**Illustrative annual premium**")
            st.bar_chart(pd.DataFrame({"₹ / year": {item["name"]: item["premium"] for item in selected}}), horizontal=True)
        st.caption("Charts compare bundled examples, not insurer quotes or current offers.")
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
        st.markdown("### Policy facts and explanations")
        policy_name = st.selectbox("Policy example", [item["name"] for item in selected], key="comparison_clause_policy")
        policy = next(item for item in selected if item["name"] == policy_name)
        for clause in policy["clauses"]:
            with st.expander(f"{clause['category']} · Page {clause['page']}"):
                fact_col, explanation_col = st.columns(2)
                with fact_col:
                    st.markdown("**Policy wording / extracted fact**")
                    st.write(clause["text"])
                    st.caption(f"{policy['source']} · {policy['version']} · Page {clause['page']}")
                with explanation_col:
                    st.markdown("**Plain-language explanation**")
                    st.write(clause["explanation"])
                    st.caption("Demonstration explanation, separate from policy wording.")
    st.markdown("### Review an uploaded policy PDF")
    _policy_upload()


def _recommendations(policies, branches, occupations, pin):
    st.markdown('<div class="eyebrow">Personalized policy shortlist</div>', unsafe_allow_html=True)
    st.title("Recommendations")
    st.caption("Set the limits a policy must meet, then tell us which features matter most. Results use demonstration records only.")
    with st.container(border=True):
        st.markdown("#### 1 · Your must-haves")
        st.caption("These are hard filters: an example outside any limit is removed before ranking.")
        first, second, third = st.columns(3)
        with first:
            age = st.number_input("Your age", min_value=18, max_value=100, value=30, step=1, key="recommend_age",
                                  help="Used only against the entry-age range listed in each example. It does not assess insurability.")
        with second:
            min_cover = st.number_input("Minimum cover (₹ lakh)", min_value=1.0, max_value=100.0, value=5.0, step=1.0,
                                        help="The minimum illustrative sum assured to keep. For example, 50 means ₹50 lakh.")
        with third:
            max_budget = st.number_input("Annual budget (₹ maximum)", min_value=1000, max_value=1000000, value=50000, step=1000,
                                         help="Examples above this annual premium are filtered out. This is not an insurer quote.")
    goals = ["Larger life cover", "Lower annual premium"]
    if any(item["category"] == "Non-term life" for item in policies):
        goals.extend(["Long-term savings and maturity value", "Periodic payouts"])
    if any(item["category"] == "Term life" for item in policies):
        goals.append("Protection duration")
    with st.container(border=True):
        st.markdown("#### 2 · Your preferences and context")
        st.caption("Preferences change the order of policies that pass your must-haves; they do not guarantee suitability.")
        left, right = st.columns(2)
        with left:
            goal = st.selectbox("Main goal", goals, help="Adds a feature-fit score based on product type and the goal you select. It does not change the insurer's terms.")
            occupation = st.selectbox("Occupation", list(occupations), key="recommend_occupation",
                                     help="Provides descriptive workplace context only. It is not used to rank, price, or determine eligibility.")
            st.caption(f"PIN/city: {pin or 'not set'} · used only to match verified local support records.")
        with right:
            use_health_context = st.checkbox("Add health disclosures as private review context", help="Optional. These details are not ranking inputs and are not sent to the AI summary service.")
            health_context = []
            if use_health_context:
                health_context = st.multiselect("Ongoing or recurring health disclosures", [
                    "Chronic condition", "Recurring condition or treatment", "Ongoing medication", "Recent or planned investigation", "Prefer to discuss directly with insurer"
                ])
                st.caption("Used only for this on-screen reminder during the active app session; not sent to AI or used to reject or rank a policy. Share relevant details directly with the insurer.")
    with st.container(border=True):
        st.markdown("#### 3 · What matters most?")
        st.caption("Set each slider from 0 to 5. Zero ignores that factor; five gives it the strongest relative influence. Equal values mean equal importance.")
        weight_cols = st.columns(4)
        weights = {
            "coverage_score": weight_cols[0].slider("Life cover", 0, 5, 3, key="weight_cover", help="How strongly should the ranking favor a larger sum assured?"),
            "price_score": weight_cols[1].slider("Lower price", 0, 5, 3, key="weight_price", help="How strongly should the ranking favor a lower example premium?"),
            "benefit_score": weight_cols[2].slider("Goal match", 0, 5, 4, key="weight_goal", help="How strongly should the selected goal influence the ranking?"),
        }
        branch_matches, _ = find_locations(branches, pin)
        if branch_matches:
            weights["local_support_score"] = weight_cols[3].slider("Local support", 0, 5, 2, key="weight_local", help="Favors an available matching branch or adviser record.")
        else:
            weight_cols[3].caption("Local support")
            weight_cols[3].markdown("No verified matches")
    # Health/occupation are retained only as non-scoring prompts for policy disclosure.
    ranked = rank_policies(policies, min_cover, max_budget, weights, age=age, goal=goal, location_records=branch_matches)
    if not ranked:
        st.warning("No example passed all three limits. Try adjusting age, minimum cover, or annual budget.")
    else:
        st.markdown("### Your ranked examples")
        st.caption("Preference fit is a relative score among the examples that passed your filters—not a probability, quality rating, or approval estimate.")
        fit = pd.DataFrame({"Preference fit / 100": {policy["name"]: policy["preference_fit"] for policy in ranked}})
        st.bar_chart(fit, horizontal=True, height=min(320, 90 + 42 * len(ranked)))
        best = ranked[0]
        with st.container(border=True):
            st.markdown(f"#### Best preference match · {best['name']}")
            left, middle, right = st.columns([3, 1, 2])
            left.caption(f"{best['product_type']} · demonstration record")
            left.write(f"Illustrative annual premium: ₹{best['premium']:,} · Cover: {best.get('sum_assured', 'Not listed')}")
            left.write(f"Premium-paying term: {best['premium_term_years']} years · Policy term: {best['policy_term_years']} years")
            middle.metric("Preference fit", f"{best['preference_fit']}/100")
            middle.progress(best["preference_fit"])
            factor_labels = {"coverage_score": "Life cover", "price_score": "Lower price", "benefit_score": "Goal match", "local_support_score": "Local support"}
            contributions = {factor_labels.get(key, key): value * weights[key] for key, value in best["score_breakdown"].items()}
            right.markdown("**Weighted factors**")
            right.bar_chart(pd.DataFrame({"Score × importance": contributions}), horizontal=True, height=210)
        if len(ranked) > 1:
            with st.expander("See other matching examples"):
                for position, policy in enumerate(ranked[1:], start=2):
                    st.markdown(f"**{position}. {policy['name']}** · preference fit {policy['preference_fit']}/100 · ₹{policy['premium']:,}/year illustrative premium")
                    st.caption(f"{policy['product_type']} · {policy['premium_term_years']} premium years · {policy['policy_term_years']} policy years")
    if ranked:
        st.caption("Age is checked against the available entry-age fields. Health disclosures and occupation are not scored; review the insurer's underwriting and disclosure requirements directly.")
    st.caption(f"Location input: {pin or 'not provided'}. Verified adviser/branch matches are included only where sourced data is available.")
    if health_context:
        st.info("Before applying, check the insurer's health questions and disclose relevant history fully. No policy eligibility conclusion is made here.")
    profile = get_profile(occupations, occupation)
    st.caption(f"Occupation context: {profile['class']} · {profile['label']} (descriptive only; not an underwriting or premium assessment).")
    st.caption("All bundled product facts and clause examples are illustrative, not insurer offers. Confirm current terms and premiums with the insurer.")
    st.caption("Demonstration amounts are not quotes. Actual terms, premiums and eligibility depend on current insurer information and underwriting.")


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
    st.title("Location and occupation")
    st.caption("Use your device location to preview a nearby search radius. Sharing location is optional.")
    search_from = st.radio("Map centre", ["Current device location", "PIN or city directory"], horizontal=True)
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
            st.caption("Device location is used in this session only. Exact coordinates are not displayed. Map tiles are not loaded from a third party.")
        else:
            st.caption("Select “Use my current location” to set the map centre, or choose PIN/city when verified directory data is available.")
    else:
        search_records, _ = find_locations(branches, pin)
        coords = location_centroid(branches, pin)
        if pin:
            st.caption("PIN/city map centre is approximate and based on directory records.")
    if coords:
        radius_km = st.slider("Preview radius (km)", 5, 50, 20, 5)
        nearby = nearby_locations(search_records, coords[0], coords[1], radius_km)
        radius = [{"lat": coords[0], "lon": coords[1], "radius_m": radius_km * 1000}]
        centre = [{"lat": coords[0], "lon": coords[1], "name": "Your selected location"}]
        layers = [
            pdk.Layer("ScatterplotLayer", data=radius, get_position="[lon, lat]", get_radius="radius_m", radius_units="meters",
                      stroked=True, filled=True, get_fill_color=[8, 127, 131, 32], get_line_color=[8, 127, 131, 190], line_width_min_pixels=2),
            pdk.Layer("ScatterplotLayer", data=centre, get_position="[lon, lat]", get_radius=230,
                      get_fill_color=[8, 127, 131, 240], get_line_color=[255, 255, 255], line_width_min_pixels=2),
        ]
        if nearby:
            layers.append(pdk.Layer("ScatterplotLayer", data=nearby, get_position="[lon, lat]", get_radius=150,
                                    get_fill_color=[236, 143, 48, 230], get_line_color=[255, 255, 255], line_width_min_pixels=1, pickable=True))
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(latitude=coords[0], longitude=coords[1], zoom=10, pitch=0),
            map_provider=None,
            tooltip={"text": "{name}\n{city} · {verified}\n{distance_km} km (straight-line estimate)"},
            height=420,
        ))
        if nearby:
            st.markdown("### Sourced insurer branches or advisers")
            for branch in nearby:
                st.markdown(f"**{branch['name']}** · {branch['city']} · {branch['distance_km']} km estimated")
                st.caption(f"Last verified: {branch['verified']} · Source: {branch['source']}")
        else:
            st.info("No verified insurer branch/adviser records are loaded. The circle shows only the selected search radius; it does not show policy or hospital coverage.")
    if not branches:
        st.caption("A source-linked directory with coordinates and last-verified dates is needed before local support results can be displayed.")
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
        page = st.radio("Workspace", ["Overview", "Policy comparison", "Recommendations", "Claim readiness", "Location & occupation"], label_visibility="collapsed", key="page_nav")
        product_focus = st.selectbox("Life policy type", ["All life policies", "Term life", "Non-term life"], key="product_focus")
        st.divider()
        st.markdown("**Your profile**")
        pin = st.text_input("PIN code or city", value="", key="pin")
        st.caption("Optional. Used only to match verified branch/adviser records; none are currently loaded.")
        st.divider()
        st.caption("Policy wording and insurer confirmation determine benefits and claim outcomes.")

    visible_policies = policies if product_focus == "All life policies" else [item for item in policies if item["category"] == product_focus]
    if page == "Overview":
        st.markdown('<div class="hero"><div class="eyebrow" style="color:#7ee2d1">Life insurance decision support</div><h1>Understand. Compare. Prepare.</h1><p>Review policy wording, see how examples differ, and prepare questions for an insurer.</p></div>', unsafe_allow_html=True)
        st.markdown("### Choose a workspace")
        a, b, c = st.columns(3)
        for col, title, body in [
            (a, "Policy comparison", "Compare terms, benefits and source wording."),
            (b, "Recommendations", "Set your constraints and rank examples by priority."),
            (c, "Claim readiness", "Review common documents for a policy request.")]:
            with col:
                st.markdown(f'<div class="panel"><h3>{title}</h3><p class="subtle">{body}</p></div>', unsafe_allow_html=True)
        st.markdown("### Reference snapshot")
        counts = market_reference["market_facts"]
        st.bar_chart(pd.DataFrame({"Listings": {"Term products": counts["term_products_listed"], "Investment plans": counts["investment_plans_listed"]}}), horizontal=True)
        st.caption(f"Policybazaar reference: {counts['term_products_listed']} term listings and {counts['investment_plans_listed']} investment-plan listings. These are market listings, not comparable policy quotes.")
        st.caption("Bundled policy and clause examples are illustrative. Uploaded wording is shown separately from its review summary.")
    elif page == "Policy comparison":
        _comparison(visible_policies, market_reference, product_focus)
    elif page == "Recommendations":
        _recommendations(visible_policies, branches, occupations, pin)
    elif page == "Claim readiness":
        _claim_readiness(visible_policies)
    else:
        _location_and_occupation(branches, occupations, pin)
    st.markdown("<br><hr><span class='subtle'>PolicyLens · Clear evidence. Better questions. More informed choices.</span>", unsafe_allow_html=True)

