"""PDF text extraction and clause organization."""

import re
import json
import urllib.error
import urllib.request


def extract_pdf_pages(pdf_bytes):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Install the project requirements to enable PDF extraction.") from exc

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for number, page in enumerate(document, start=1):
        content = page.get_text("text").strip()
        pages.append({"page": number, "text": content, "has_text": bool(content)})
    return pages


def classify_page_text(text):
    """Assign a review category using transparent keyword rules."""
    normalized = text.lower()
    terms = {
        "Premium payment": ("premium", "grace period", "premium-paying"),
        "Maturity benefit": ("maturity benefit", "survival benefit", "maturity proceeds"),
        "Surrender": ("surrender value", "surrender benefit", "paid-up value"),
        "Bonus": ("reversionary bonus", "terminal bonus", "bonus"),
        "Exclusion": ("excluded", "exclusion", "not covered"),
        "Death benefit": ("death benefit", "sum assured on death", "death claim"),
        "Claims process": ("claim form", "claim procedure", "death certificate", "maturity claim"),
        "Policy loan": ("policy loan", "loan against policy"),
    }
    for category, phrases in terms.items():
        if any(phrase in normalized for phrase in phrases):
            return category
    return "Other policy wording"


def make_review_note(category):
    """Return a non-generative review prompt; custom uploads are not AI explained."""
    return (f"Review the complete {category.lower()} clause and any related schedule or endorsement. "
            "This note is a navigation aid, not a generated interpretation.")


def split_text_blocks(text):
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def summarize_policy_text(text, api_key, model):
    """Summarize one user-selected page through the configured OpenAI Responses API."""
    if not api_key or not model:
        raise RuntimeError("AI summary is not configured. Set OPENAI_API_KEY and OPENAI_MODEL in the app secrets.")
    content = (text or "").strip()
    if not content:
        raise ValueError("There is no extracted text to summarize.")
    if len(content) > 18000:
        content = content[:18000]

    payload = {
        "model": model,
        "instructions": (
            "Explain the supplied life insurance policy page in plain language. "
            "Use only information present in the text. Separate stated facts from implications; "
            "preserve conditions, exclusions, amounts, and uncertainty. Do not infer coverage, "
            "claim approval, eligibility, or financial advice. If wording is unclear, say so."
        ),
        "input": content,
        "max_output_tokens": 500,
        "store": False,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError("The AI service rejected the configured credentials. Check the app secrets.") from error
        if error.code == 429:
            raise RuntimeError("The AI service is temporarily rate-limited. Please try again later.") from error
        raise RuntimeError("The AI summary service could not complete this request.") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("The AI summary service could not be reached. Please try again later.") from error

    output = result.get("output_text", "").strip()
    if not output:
        output = "\n".join(
            part.get("text", "")
            for item in result.get("output", [])
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ).strip()
    if not output:
        raise RuntimeError("The AI service returned no summary for this page.")
    return output

