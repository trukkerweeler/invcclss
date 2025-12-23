"""Invoice classification and date extraction functionality."""

import json
import os
import re
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import PROFILE_PATH, DATE_PATTERNS, DATE_FORMATS, DATE_OUTPUT_FORMAT
from db import get_classification_profiles, save_classification_profiles


def save_profiles(samples):
    """Save supplier profiles to JSON file."""
    # Persist to SQLite via db module
    try:
        save_classification_profiles(samples)
    except Exception:
        # Fallback: write JSON file
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(samples, f, indent=2)


def load_profiles():
    """Load supplier profiles from JSON file."""
    try:
        return get_classification_profiles()
    except Exception:
        # Fallback to JSON file if DB unavailable
        if not os.path.exists(PROFILE_PATH):
            return {}
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            return {}


def train_supplier_profiles(profiles):
    """Train TF-IDF vectorizer on supplier profiles."""
    texts, labels = [], []
    for supplier, texts_list in profiles.items():
        for text in texts_list:
            texts.append(text)
            labels.append(supplier)
    vectorizer = TfidfVectorizer().fit(texts)
    vectors = vectorizer.transform(texts)
    return vectorizer, vectors, labels


def classify_invoice(text, vectorizer, sample_vectors, sample_labels, threshold=0.3):
    """Classify invoice and extract date from text.

    Args:
        text: Invoice text to classify
        vectorizer: Trained TF-IDF vectorizer
        sample_vectors: Training data vectors
        sample_labels: Supplier labels for training data
        threshold: Minimum confidence score (0-1) to accept classification

    Returns:
        tuple: (supplier_name, invoice_date, confidence_score) where supplier is 'UNKNOWN' if below threshold
    """
    vec = vectorizer.transform([text])
    scores = cosine_similarity(vec, sample_vectors)[0]  # Get scores array
    best_index = scores.argmax()
    best_score = scores[best_index]

    # Return UNKNOWN if confidence is below threshold
    best_supplier = sample_labels[best_index] if best_score >= threshold else "UNKNOWN"
    invoice_date = extract_invoice_date(text)
    return best_supplier, invoice_date, best_score


def extract_invoice_date(text):
    """Extract invoice date from text using configured patterns."""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1).strip()
            # Remove trailing text like "Page 1 of 3"
            raw_date = re.split(r"\s+Page\b", raw_date,
                                flags=re.IGNORECASE)[0].strip()

            # If the captured text contains multiple parts (like table row), extract just the date
            # Look for date patterns within the captured text
            date_in_text = re.search(
                r"\b(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}|\w{3,9}\s+\d{1,2},?\s+\d{4})\b",
                raw_date,
                re.IGNORECASE,
            )
            if date_in_text:
                raw_date = date_in_text.group(1).strip()

            # Fix common OCR errors in month names and punctuation
            ocr_fixes = {
                r"\bOst\b": "Oct",  # O-s-t -> Oct
                r"\bDes\b": "Dec",  # D-e-s -> Dec
                r"\bAuy\b": "Aug",  # A-u-y -> Aug
                r"\bJan\b": "Jan",  # Already correct
                r"\bFeb\b": "Feb",
                r"\bMar\b": "Mar",
                r"\bApr\b": "Apr",
                r"\bMay\b": "May",
                r"\bJun\b": "Jun",
                r"\bJul\b": "Jul",
                r"\bAug\b": "Aug",
                r"\bSep\b": "Sep",
                r"\bNov\b": "Nov",
            }

            for pattern, replacement in ocr_fixes.items():
                raw_date = re.sub(pattern, replacement,
                                  raw_date, flags=re.IGNORECASE)

            # Fix extra comma before year (e.g., "Jun 2,-2025" -> "Jun 2, 2025")
            raw_date = re.sub(r",\s*-\s*", ", ", raw_date)

            try:
                # Try parsing with multiple formats
                for fmt in DATE_FORMATS:
                    try:
                        dt = datetime.strptime(raw_date, fmt)
                        return dt.strftime(DATE_OUTPUT_FORMAT)
                    except ValueError:
                        continue
            except Exception:
                pass
    return None
