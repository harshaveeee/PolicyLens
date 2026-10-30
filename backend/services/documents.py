"""PDF text extraction and clause organization."""

import re


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
