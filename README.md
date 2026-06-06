# Synthetic PII Token Generator

A REST API and CLI tool that detects PII/PHI/PCI in text and replaces each entity with a realistic synthetic value — not a placeholder like `[REDACTED]`, but a fake name, email, credit card number, etc. of the same type.

Built on **GLiNER** (ML-based NER) + **Presidio** + **Faker**.

---

## Supported Entity Types

| Category | Entities |
|---|---|
| Identity | PERSON, AGE, GENDER, NATIONALITY, PASSPORT |
| Contact | EMAIL_ADDRESS, PHONE_NUMBER |
| Location | LOCATION |
| Medical | DIAGNOSIS, MEDICATION, BLOOD_TYPE, MEDICAL_RECORD_NUMBER, HEALTH_PLAN_NUMBER |
| Financial | CREDIT_CARD, IBAN, SWIFT_CODE, BANK_ACCOUNT, CRYPTO_ADDRESS, TAX_IDENTIFIER |
| Network | IP_ADDRESS, MAC_ADDRESS, URL |
| Temporal | DATE_TIME |
| Auth | PASSWORD |
| Organization | ORGANIZATION |

---

## Setup

**1. Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

**2. Install dependencies**
```bash
pip install -r requirementspiiapi.txt
```

**3. Download the spaCy model**
```bash
python -m spacy download en_core_web_lg
```

**4. (Optional) GLiNER via HuggingFace**

GLiNER improves detection of medical and custom entities. It loads automatically if the `gliner` package is installed. If your model requires authentication, set:
```bash
export HUGGINGFACE_TOKEN=hf_...
```
Without GLiNER the service falls back to spaCy NER + Presidio built-in recognizers.

---

## Running the API

```bash
uvicorn api:app --reload
```

Server starts at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns pipeline ready status |
| `GET` | `/entities` | Lists all 24 supported entity types |
| `POST` | `/detect` | Detects PII entities in text |
| `POST` | `/anonymize` | Replaces PII with synthetic tokens |
| `POST` | `/both` | Detects and anonymizes in one call |

### Request body (all POST endpoints)
```json
{ "text": "your text here" }
```

### Examples

```bash
# Health check
curl http://localhost:8000/health

# Detect PII
curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Call John Smith at john@example.com or +1-555-867-5309"}'

# Anonymize
curl -X POST http://localhost:8000/anonymize \
  -H "Content-Type: application/json" \
  -d '{"text": "Call John Smith at john@example.com or +1-555-867-5309"}'

# Detect + anonymize in one call
curl -X POST http://localhost:8000/both \
  -H "Content-Type: application/json" \
  -d '{"text": "Call John Smith at john@example.com or +1-555-867-5309"}'
```

### Sample response — `/detect`
```json
{
  "entities": [
    { "entity_type": "PERSON", "start": 5, "end": 15, "score": 0.91, "value": "John Smith" },
    { "entity_type": "EMAIL_ADDRESS", "start": 19, "end": 34, "score": 0.99, "value": "john@example.com" },
    { "entity_type": "PHONE_NUMBER", "start": 38, "end": 54, "score": 0.85, "value": "+1-555-867-5309" }
  ],
  "count": 3
}
```

### Sample response — `/anonymize`
```json
{
  "anonymized_text": "Call Patricia Moore at miller@example.net or +1-800-234-5678"
}
```

---

## CLI Usage

Run the demo script directly against built-in test cases:

```bash
python synthetic_pii_generator.py --mode both
```

Or pass your own text:

```bash
python synthetic_pii_generator.py --mode both --text "Patient Alice Smith, DOB March 3, 1979"
```

**Modes:**
- `detect` — report entities only, no replacement
- `anonymize` — replace entities, show detections for reference
- `both` — report entities then show anonymized text (default)

---

## How It Works

1. **Detection** — GLiNER (ML) detects contextual entities (PERSON, ORGANIZATION, DIAGNOSIS, etc.). Presidio regex recognizers handle structured patterns (EMAIL, IBAN, PASSPORT, MAC, etc.).
2. **Conflict resolution** — when entities overlap, Presidio keeps the higher-confidence detection.
3. **Synthesis** — each detected span is replaced with a realistic fake value of the same type using Faker and custom generators. Replacements are random per call and not deterministic across requests.

---

## Known Limitations

- **BANK_ACCOUNT** — GLiNER may occasionally detect IBAN spans as BANK_ACCOUNT; conflict resolution ensures the correct replacement.
- **Short names in context** — PERSON detection can miss names that appear after labels like "Contact:" at low confidence.
- **Non-English text** — only English is supported.
- **Synthetic values are not deterministic** — the same input will produce different synthetic outputs on each call.
