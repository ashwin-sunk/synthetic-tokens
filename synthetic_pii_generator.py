"""
Synthetic PII/PHI/PCI token generator using GLiNER + Presidio + Faker.

Install dependencies:
    pip install gliner presidio-analyzer presidio-anonymizer faker spacy
    python -m spacy download en_core_web_lg

GLiNER (optional, improves medical/custom entity detection):
    Requires a HuggingFace account and token set via:
        export HUGGINGFACE_TOKEN=hf_...
    or: huggingface-cli login
    Falls back to spaCy NER + regex recognizers if unavailable.
"""

from __future__ import annotations

import os
import random
import string

from faker import Faker
from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

_gliner_model = None
_GLINER_MODEL_ID = "urchade/gliner_medium-v2.1"

def _try_load_gliner():
    global _gliner_model
    hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    try:
        from gliner import GLiNER
        kwargs = {"token": hf_token} if hf_token else {}
        _gliner_model = GLiNER.from_pretrained(_GLINER_MODEL_ID, **kwargs)
        print(f"[INFO] GLiNER loaded: {_GLINER_MODEL_ID}")
    except ImportError:
        print("[INFO] gliner package not installed — using spaCy NER fallback.")
    except Exception as e:
        hint = " Set HUGGINGFACE_TOKEN env var to authenticate." if "401" in str(e) else ""
        print(f"[INFO] GLiNER unavailable ({type(e).__name__}).{hint} Using spaCy NER fallback.")

_try_load_gliner()

fake = Faker()

# ---------------------------------------------------------------------------
# Entity catalogue
# ---------------------------------------------------------------------------

# Entities GLiNER base model handles reasonably well
GLINER_SUPPORTED = [
    "PERSON", "LOCATION", "ORGANIZATION", "DATE_TIME",
    "PHONE_NUMBER",
    "IP_ADDRESS", "CREDIT_CARD",
    "AGE", "GENDER", "NATIONALITY",
    "DIAGNOSIS", "MEDICATION", "BLOOD_TYPE",
    "BANK_ACCOUNT", "CRYPTO_ADDRESS",
]

# Entities that rely on regex/pattern matching (added via Presidio built-ins or below)
PATTERN_BASED = [
    "EMAIL_ADDRESS", "URL", "PASSPORT", "IBAN",
    "SWIFT_CODE", "TAX_IDENTIFIER", "HEALTH_PLAN_NUMBER",
    "MEDICAL_RECORD_NUMBER", "MAC_ADDRESS", "PASSWORD",
]

ALL_ENTITIES = GLINER_SUPPORTED + PATTERN_BASED

# ---------------------------------------------------------------------------
# GLiNER-backed Presidio recognizer
# ---------------------------------------------------------------------------

class GLiNERRecognizer(EntityRecognizer):
    """Presidio recognizer that delegates NER to GLiNER."""

    THRESHOLD = 0.75

    def __init__(self):
        super().__init__(supported_entities=GLINER_SUPPORTED, name="GLiNERRecognizer")

    def load(self):
        pass  # model loaded at module level

    def analyze(self, text: str, entities: list[str], nlp_artifacts=None) -> list[RecognizerResult]:
        if _gliner_model is None:
            return []
        targets = [e for e in entities if e in GLINER_SUPPORTED]
        if not targets:
            return []
        hits = _gliner_model.predict_entities(text, targets, threshold=self.THRESHOLD)
        return [
            RecognizerResult(
                entity_type=h["label"],
                start=h["start"],
                end=h["end"],
                score=h["score"],
            )
            for h in hits
        ]

# ---------------------------------------------------------------------------
# Regex-based recognizer for pattern entities not covered by GLiNER
# ---------------------------------------------------------------------------

import re
from presidio_analyzer import Pattern, PatternRecognizer

_DIAGNOSIS_TERMS = [
    "hypertension", "type 2 diabetes", "type 1 diabetes", "diabetes mellitus",
    "asthma", "chronic kidney disease", "atrial fibrillation", "copd",
    "osteoarthritis", "major depressive disorder", "hypothyroidism",
    "acute bronchitis", "pneumonia", "anemia", "anxiety disorder",
    "heart failure", "coronary artery disease", "stroke", "epilepsy",
    "gastroesophageal reflux disease", "gerd", "acute bronchitis",
]

def _make_diagnosis_recognizer() -> PatternRecognizer:
    pattern = r"(?i)\b(" + "|".join(re.escape(t) for t in _DIAGNOSIS_TERMS) + r")\b"
    return PatternRecognizer(
        supported_entity="DIAGNOSIS",
        patterns=[Pattern(name="DIAGNOSIS_KEYWORD", regex=pattern, score=0.85)],
    )

def _make_pattern_recognizers() -> list[PatternRecognizer]:
    specs = [
        ("EMAIL_ADDRESS",         r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        ("URL",                   r"https?://[^\s]*[^\s.,;:!?)\]]|www\.[^\s]*[^\s.,;:!?)\]]"),
        ("PASSPORT",              r"(?-i)\b[A-Z]{1,2}\d{6,9}\b"),
        ("IBAN",                  r"(?-i)\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        ("SWIFT_CODE",            r"(?-i)\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b"),
        ("TAX_IDENTIFIER",        r"\b\d{2}-\d{7}\b|\b\d{3}-\d{2}-\d{4}\b"),
        ("HEALTH_PLAN_NUMBER",    r"\b[A-Z]{3}\d{9,12}\b"),
        ("MEDICAL_RECORD_NUMBER", r"\bMRN[-:]?\s*\d{6,10}\b"),
        ("MAC_ADDRESS",           r"\b([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b"),
        ("PASSWORD",              r"(?i)password\s*[=:]\s*\S+"),
    ]
    # Regex-based entities get 0.99 to beat GLiNER scores on overlapping spans
    HIGH_SCORE = {"EMAIL_ADDRESS", "URL", "TAX_IDENTIFIER", "IBAN"}
    recognizers = []
    for entity, pattern in specs:
        recognizers.append(
            PatternRecognizer(
                supported_entity=entity,
                patterns=[Pattern(name=entity, regex=pattern, score=0.99 if entity in HIGH_SCORE else 0.7)],
            )
        )
    return recognizers

# ---------------------------------------------------------------------------
# Synthetic token routing
# ---------------------------------------------------------------------------

def _random_hex(n: int) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))

def _synth_swift() -> str:
    bank = "".join(random.choices(string.ascii_uppercase, k=4))
    country = random.choice(["US", "GB", "DE", "FR", "SG"])
    loc = "".join(random.choices(string.ascii_uppercase + string.digits, k=2))
    return f"{bank}{country}{loc}"

def _synth_tax_id() -> str:
    return f"{random.randint(10,99)}-{random.randint(1000000,9999999)}"

def _synth_health_plan() -> str:
    prefix = "".join(random.choices(string.ascii_uppercase, k=3))
    return f"{prefix}{random.randint(100000000, 999999999)}"

def _synth_mrn() -> str:
    return f"MRN-{random.randint(100000, 9999999)}"

def _synth_mac() -> str:
    return ":".join(f"{random.randint(0,255):02x}" for _ in range(6))

SYNTH_MAP: dict[str, callable] = {
    "PERSON":               fake.name,
    "LOCATION":             fake.city,
    "ORGANIZATION":         fake.company,
    "DATE_TIME":            lambda: fake.date_time_this_decade().strftime("%B %d, %Y %H:%M"),
    "AGE":                  lambda: f"age {random.randint(18, 90)}",
    "GENDER":               lambda: random.choice(["Male", "Female", "Non-binary"]),
    "NATIONALITY":          fake.country,
    "CREDIT_CARD":          fake.credit_card_number,
    "BANK_ACCOUNT":         fake.bban,
    "IBAN":                 fake.iban,
    "SWIFT_CODE":           _synth_swift,
    "TAX_IDENTIFIER":       _synth_tax_id,
    "CRYPTO_ADDRESS":       lambda: f"0x{_random_hex(40)}",
    "MEDICAL_RECORD_NUMBER": _synth_mrn,
    "HEALTH_PLAN_NUMBER":   _synth_health_plan,
    "DIAGNOSIS":            lambda: random.choice([
                                "Hypertension", "Type 2 Diabetes", "Asthma", "Chronic Kidney Disease",
                                "Atrial Fibrillation", "COPD", "Osteoarthritis", "Major Depressive Disorder",
                                "Hypothyroidism", "Gastroesophageal Reflux Disease",
                            ]),
    "MEDICATION":           lambda: random.choice([
                                "Metformin 500mg", "Lisinopril 10mg", "Atorvastatin 20mg",
                                "Amlodipine 5mg", "Omeprazole 20mg", "Levothyroxine 50mcg",
                                "Sertraline 100mg", "Albuterol 90mcg", "Gabapentin 300mg",
                                "Furosemide 40mg",
                            ]),
    "BLOOD_TYPE":           lambda: f"blood type {random.choice(['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'])}",
    "IP_ADDRESS":           fake.ipv4,
    "MAC_ADDRESS":          _synth_mac,
    "EMAIL_ADDRESS":        fake.email,
    "PHONE_NUMBER":         fake.phone_number,
    "URL":                  fake.url,
    "PASSWORD":             lambda: f"password={fake.password()}",
    "PASSPORT":             lambda: fake.bothify(text="??#######").upper(),
}

def synthesize(matched_text: str, entity_type: str) -> str:
    fn = SYNTH_MAP.get(entity_type)
    if fn:
        return fn()
    return f"[SYNTHETIC_{entity_type}]"

# ---------------------------------------------------------------------------
# Pipeline setup
# ---------------------------------------------------------------------------

def build_pipeline():
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    })
    nlp_engine = provider.create_engine()

    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    if _gliner_model is not None:
        # GLiNER covers NER — remove overlapping Presidio built-ins to avoid duplicates
        # Remove spaCy (GLiNER handles NER) and our regex-covered types.
        # Keep PhoneRecognizer, IpRecognizer, IbanRecognizer, CreditCardRecognizer
        # as reliable regex fallbacks for entities GLiNER may miss.
        overlap = {"SpacyRecognizer", "EmailRecognizer", "UrlRecognizer", "IbanRecognizer"}
        analyzer.registry.recognizers = [
            r for r in analyzer.registry.recognizers
            if r.__class__.__name__ not in overlap
        ]
        analyzer.registry.add_recognizer(GLiNERRecognizer())
        print("[INFO] Using GLiNER + spaCy + regex recognizers.")
    else:
        # spaCy fallback: keep Presidio built-ins (EMAIL, PHONE, IP, CREDIT_CARD, IBAN, URL)
        # spaCy en_core_web_lg handles PERSON, ORG, GPE (→ LOCATION), DATE natively
        print("[INFO] Using spaCy built-ins + Presidio built-in recognizers (no GLiNER).")

    for pr in _make_pattern_recognizers():
        analyzer.registry.add_recognizer(pr)
    analyzer.registry.add_recognizer(_make_diagnosis_recognizer())

    anonymizer = AnonymizerEngine()

    operators = {
        ent: OperatorConfig("custom", {"lambda": lambda x, e=ent: synthesize(x, e)})
        for ent in ALL_ENTITIES
    }

    return analyzer, anonymizer, operators

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_pii(text: str, analyzer) -> list:
    """Return detected PII entities without modifying the text."""
    return analyzer.analyze(text=text, language="en", entities=ALL_ENTITIES)

def anonymize_text(text: str, analyzer, anonymizer, operators) -> tuple[str, list]:
    """Detect PII and replace each entity with a synthetic token."""
    results = detect_pii(text, analyzer)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    return anonymized.text, results

def print_detections(text: str, findings: list) -> None:
    """Print a formatted detection report for the given text and findings."""
    if not findings:
        print("  (no PII entities detected)")
        return
    for f in sorted(findings, key=lambda x: x.start):
        print(f"  {f.entity_type:30s}  score={f.score:.2f}  "
              f"value='{text[f.start:f.end]}'")

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Synthetic PII token generator")
    parser.add_argument(
        "--mode",
        choices=["detect", "anonymize", "both"],
        default="both",
        help=(
            "detect  — report PII entities only, no replacement\n"
            "anonymize — replace PII with synthetic tokens, no report\n"
            "both    — report entities then show anonymized text (default)"
        ),
    )
    parser.add_argument("--text", type=str, default=None,
                        help="Text to process (uses built-in test cases if omitted)")
    args = parser.parse_args()

    print("Building pipeline...")
    analyzer, anonymizer, operators = build_pipeline()

    if args.text:
        test_cases = [args.text]
    else:
        test_cases = [
            (
                "Patient Alice Smith, DOB March 3, 1979, female, was prescribed Amoxicillin 250mg "
                "for a diagnosis of Acute Bronchitis. Her MRN is MRN-4820193 and health plan is BCV123456789. "
                "Bill to IBAN GB29NWBK60161331926819 (SWIFT: BARCGB22). "
                "Notify her at alice.smith@email.com or +1-555-867-5309. "
                "Last login from IP 192.168.1.42, MAC 00:1A:2B:3C:4D:5E. "
                "Crypto refund to 0x71C7656EC7ab88b098defB751B7401B5f6d8976F."
            ),
            (
                "John Doe's SSN/TIN is 52-3891024. His passport number is AB1234567. "
                "System credentials: password=S3cur3P@ss! accessed from http://internal.corp/admin."
            ),
            (
                "Patient Maria Gonzalez, born January 15, 1985, female, American, age 39, blood type O+, "
                "was diagnosed with Type 2 Diabetes and prescribed Metformin 500mg. "
                "Her MRN is MRN-7291048 and health plan is XYZ987654321. "
                "Contact her at maria.gonzalez@hospital.org or call +1-800-555-1234. "
                "She lives at 742 Evergreen Terrace, Springfield. "
                "Payment details: IBAN DE89370400440532013000 (SWIFT: COBADEFFXXX), "
                "credit card 4111111111111111, bank account NWBK60161331926819, "
                "crypto wallet 0xAbCdEf1234567890AbCdEf1234567890AbCdEf12. "
                "Tax ID: 52-1234567, passport AB9876543. "
                "Last login from IP 10.0.0.1, MAC AA:BB:CC:DD:EE:FF, "
                "system URL https://secure.internal.example.com/dashboard. "
                "Credentials: password=MyS3cr3tP@ss! "
                "Billing contact: John Smith (john.smith@billing.com), nationality Canadian."
            ),
        ]

    for i, raw in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test case {i}")
        print(f"{'='*60}")
        print("[Original]\n", raw)

        if args.mode in ("detect", "both"):
            findings = detect_pii(raw, analyzer)
            print(f"\n[Detected PII — {len(findings)} entities]")
            print_detections(raw, findings)

        if args.mode in ("anonymize", "both"):
            synth, findings = anonymize_text(raw, analyzer, anonymizer, operators)
            if args.mode == "anonymize":
                # Print detections only for reference when in anonymize-only mode
                print(f"\n[Detected PII — {len(findings)} entities]")
                print_detections(raw, findings)
            print("\n[Synthetic output]\n", synth)
