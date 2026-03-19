# Implementation Plan: LLM Rule Suggestion Engine

## Architectural Change Summary

**Before:** Classification pipeline assigns GL codes via two layers — deterministic rules, then LLM inference for unmatched transactions. LLM directly classifies transactions.

**After:** LLM is removed from the classification loop entirely. Every GL code assignment traces to a rule or a manual user decision. LLM's new role is twofold:
1. **Rule Suggestion Engine** — For unmatched transactions, LLM suggests new rules for the user to review/approve before reclassifying.
2. **Conflict Advisor** — For multi-rule-match transactions (Medium confidence), LLM provides advisory text to help the user decide, but does NOT make the classification.

## Confidence Score Redefinition

- **High** — Single rule match, no ambiguity. GL code assigned automatically.
- **Medium** — Multiple rules matched with conflicting GL codes. GL code assigned from most specific rule, but flagged for review. LLM advisory text explains which rule is more likely correct based on historical patterns.
- **Low** — No rule match. Transaction is unclassified (gl_code = NULL). User must either create/update rules and re-run classification, or manually classify the transaction.

---

## 1. Backend Changes

### 1.1 Remove LLM from Classification Pipeline

**File: `backend/services/classification.py`**

Modify the pipeline orchestrator. The flow becomes:

1. Non-expense detection (unchanged)
2. Vendor resolution (unchanged — cache-first, LLM fallback for new descriptions)
3. Rule engine classification (unchanged logic, but it's now the ONLY classification step)
4. **NEW:** For Medium confidence transactions (rule conflicts), call LLM for advisory text only
5. Unmatched transactions get: `gl_code = NULL`, `confidence = 'Low'`, `method = 'Unclassified'`, `review_status = 'Flagged'`

Remove the step that sends unmatched transactions to `llm_classifier.py` for GL code assignment.

### 1.2 Repurpose LLM Classifier → Rule Suggestion Service

**File: `backend/services/llm_rule_suggester.py`** (rename or replace `llm_classifier.py`)

New service that takes a batch of unclassified transactions and returns suggested rules.

```python
def suggest_rules(unclassified_transactions, existing_rules, existing_vendors, gl_codes, historical_transactions):
    """
    Send unclassified transactions to LLM. LLM returns suggested rules, NOT classifications.
    Transactions are grouped by vendor to produce one rule suggestion per vendor pattern.
    """
```

**LLM Prompt:**

```
System: You are a rule suggestion engine for a GL code classification system at a small insurance agency.

You will receive:
1. A batch of unclassified transactions (no existing rule matched)
2. The current rules table (so you don't suggest duplicates)
3. Historical classified transactions for context
4. The GL code hierarchy

Your job is to suggest NEW classification rules that would correctly classify these transactions.
Do NOT classify individual transactions. Instead, suggest rules that cover patterns.

For each suggested rule, provide:
- vendor_id: The vendor ticker to match (must reference an existing vendor)
- service_id: Optional service ticker for more specific matching
- amount_min / amount_max: Optional amount range if relevant
- gl_code: The target GL code
- reasoning: Why this rule makes sense — reference historical patterns, vendor business type, GL code descriptions
- affected_transactions: List of transaction_ids this rule would classify

Group transactions by vendor. One rule per vendor pattern. If a vendor needs multiple rules (different services or amount ranges), suggest each separately.

Be conservative. If you're unsure about a GL code, say so in the reasoning and let the user decide.

Respond in JSON only — an array of suggested rules:
[
  {
    "vendor_id": "COMCST",
    "service_id": null,
    "amount_min": null,
    "amount_max": null,
    "gl_code": 6260,
    "reasoning": "Comcast transactions without a service-level match appear to be cable/utility charges. Historical data shows 4 Comcast transactions at $42-70 coded to 6260 (Utilities). Suggest defaulting unmatched Comcast to 6260.",
    "affected_transactions": ["NEW-045", "NEW-089", "NEW-102"]
  },
  ...
]
```

### 1.3 Conflict Advisor Service

**File: `backend/services/llm_conflict_advisor.py`** (new file)

For Medium confidence transactions (multiple rules, conflicting GL codes), generate advisory text.

```python
def advise_on_conflicts(conflicting_transactions, matching_rules, historical_transactions, gl_codes):
    """
    For each transaction with conflicting rule matches, generate an advisory string
    explaining which rule is more likely correct and why. Does NOT change the classification.
    Advisory text is stored in the transaction's reasoning field.
    """
```

**LLM Prompt:**

```
System: You are an advisory engine helping accountants resolve GL code classification conflicts.

For each transaction below, multiple classification rules matched with different GL codes.
Your job is to explain which GL code is more likely correct and why, referencing historical patterns and the nature of the transaction. You are NOT making the decision — the user will decide.

For each transaction, provide:
- transaction_id
- recommended_gl_code: Your best assessment
- advisory: 2-3 sentence explanation. Reference the specific conflicting rules, historical patterns, and vendor context.

Respond in JSON only:
[
  {
    "transaction_id": "NEW-045",
    "recommended_gl_code": 6260,
    "advisory": "Rules R-14 (GL 6200, Comcast Internet) and R-22 (GL 6260, Comcast Cable) both match. This transaction at $69.70 is consistent with the $42-70 range of 4 historical Comcast cable charges coded to 6260. Consider adding service-level differentiation to the Comcast rules."
  }
]
```

**Integration:** After the rule engine runs, collect all Medium confidence transactions. If there are any, send them to the conflict advisor in a single batched call. Store the advisory text in the transaction's `reasoning` field alongside the conflict detail.

### 1.4 New API Endpoints

**File: `backend/routers/classify.py`** (add endpoints)

```
POST /api/suggest-rules
```
- Triggers the rule suggestion engine for all currently unclassified (Low confidence) transactions
- Returns: array of suggested rules with reasoning and affected transaction counts
- Does NOT create rules — just returns suggestions for UI display

```
POST /api/suggest-rules/accept
```
- Body: `{ suggestions: [{ vendor_id, service_id, amount_min, amount_max, gl_code }] }`
- Creates the accepted rules in the classification_rules table
- Returns: created rule IDs

```
POST /api/reclassify
```
- Triggers re-run of the rule engine on all unclassified (Low confidence) and Flagged transactions
- Uses the current rules table (including any newly accepted rules)
- Returns: classification summary (how many moved from Low to High, how many still unmatched)

**File: `backend/schemas.py`** (add models)

```python
class RuleSuggestion(BaseModel):
    vendor_id: str
    vendor_name: str  # For display
    service_id: Optional[str]
    service_name: Optional[str]  # For display
    amount_min: Optional[float]
    amount_max: Optional[float]
    gl_code: int
    gl_class: str  # For display
    reasoning: str
    affected_transaction_ids: List[str]
    affected_count: int

class SuggestRulesResponse(BaseModel):
    suggestions: List[RuleSuggestion]
    total_unclassified: int

class AcceptSuggestionsRequest(BaseModel):
    suggestions: List[dict]  # Subset of suggestions the user accepted (possibly edited)
    user_id: int
```

### 1.5 Update Transaction Method Values

Add `'Unclassified'` as a valid method value in the transactions table check constraint and SQLAlchemy model:

```sql
CHECK (method IN ('Rule Match', 'LLM Inference', 'Unclassifiable', 'Unclassified', 'Pre-classified', 'Manual'))
```

- `Rule Match` — classified by deterministic rule (High or Medium confidence)
- `Unclassified` — no rule matched (Low confidence, gl_code = NULL)
- `Pre-classified` — uploaded with GL code from CSV
- `Manual` — user manually assigned GL code without creating a rule
- `Unclassifiable` — non-expense transaction (AUTOPAY etc.)
- `LLM Inference` — legacy, keep for backward compatibility with existing data but no longer generated

### 1.6 Update Rule Engine

**File: `backend/services/rule_engine.py`**

The conflict case (multiple rules, different GL codes) now additionally stores the conflicting rule details in a structured way that the conflict advisor can use:

```python
# In the conflict branch, store structured conflict data
return {
    'gl_code': most_specific_rule.gl_code,  # Best guess from most specific rule
    'confidence': 'Medium',
    'method': 'Rule Match',
    'rule_id': most_specific_rule.rule_id,
    'reasoning': f'RULE CONFLICT: {conflict_detail}. Review recommended.',
    'review_status': 'Flagged',
    'conflict_rules': matching_rules  # Pass to conflict advisor
}
```

---

## 2. Frontend Changes

### 2.1 New Workflow: Suggest & Accept Rules

The transaction upload flow becomes a 3-step process:

**Step 1: Upload CSV** (existing — drag-and-drop)
**Step 2: Process Transactions** (existing — runs vendor resolution + rule engine)
**Step 3: Review Suggestions** (NEW — if unclassified transactions exist, show rule suggestions)

### 2.2 Rule Suggestions Panel

**File: `frontend/src/components/transactions/RuleSuggestionsPanel.jsx`** (new)

After classification runs, if there are Low confidence (unclassified) transactions, show a panel/modal:

**Header:** "X transactions could not be classified. Review suggested rules below."

**For each suggestion, display as a card:**
- Vendor name + Service (if any)
- Suggested GL Code + GL Class name
- Amount range (if specified)
- LLM reasoning text
- Number of affected transactions (clickable to show list)
- Actions: **Approve** (creates rule as-is), **Edit & Approve** (opens rule form prepopulated), **Reject** (dismiss suggestion)

**Footer actions:**
- "Approve All" — batch approve all suggestions
- "Re-classify" — after approving some/all, re-run classification on remaining unclassified transactions
- "Dismiss" — close panel, leave transactions unclassified for manual review

### 2.3 Transactions Table Updates

**File: `frontend/src/pages/TransactionsPage.jsx`**

- Unclassified transactions (Low confidence, gl_code = NULL) should display GL Code column as "—" or a chip reading "Unclassified" rather than empty
- Medium confidence transactions should show the advisory text in the expandable reasoning row, styled distinctly from standard reasoning (e.g., a light blue advisory callout: "LLM Advisory: ...")
- Add a banner at the top of the table when unclassified transactions exist: "N transactions need rules. [Suggest Rules]" — clicking triggers the suggest-rules flow

### 2.4 Updated Upload Flow

**File: `frontend/src/pages/TransactionsPage.jsx`**

Modify the staged file card's flow to be 3 steps:

1. **Upload CSV** → "Process Transactions" button (existing)
2. **Process** → runs classification pipeline → show results summary
3. **Results summary** shows: X classified by rules (High), Y conflicts (Medium), Z unclassified (Low), W non-expense
4. If Z > 0, show "Suggest Rules for Z unclassified transactions" button → opens RuleSuggestionsPanel
5. After user approves/edits rules → "Re-classify" button re-runs rule engine → updated summary

### 2.5 Conflict Advisory in Transaction Detail

When a user expands a Medium confidence transaction row, the detail panel should show:

- The conflicting rules (Rule R-14: GL 6200, Rule R-22: GL 6260)
- The LLM advisory text in a visually distinct callout (not as the primary reasoning, but as a helper)
- Action buttons: "Approve Current" (accept the most-specific-rule assignment) or "Reclassify" (pick a different GL code)

### 2.6 Stats Bar Update

Update the stats bar to reflect the new confidence semantics. Ensure:
- "Low" count reflects truly unclassified transactions, not LLM low-confidence guesses
- Consider adding "Unclassified" as a separate stat alongside the confidence breakdown

---

## 3. Batch Identifier Change

### Current State
The `source_file` field on transactions stores the CSV filename (e.g., `classify.csv`). The batch filter dropdown shows distinct filenames. Re-uploading the same file overwrites the filter — all uploads of `classify.csv` appear as one batch.

### Change
Replace `source_file` (or supplement it) with a proper **batch identifier** that combines filename + upload timestamp.

**Backend:**

**File: `backend/models.py`** — Add `upload_batch` column to the transactions table:

```python
upload_batch = Column(String(255))  # Format: "filename.csv (Mar 19, 2026 2:45 PM)"
```

**File: `backend/routers/classify.py`** — On CSV upload, generate the batch label:

```python
from datetime import datetime

batch_label = f"{file.filename} ({datetime.now().strftime('%b %d, %Y %I:%M %p')})"
# e.g., "classify.csv (Mar 19, 2026 2:45 PM)"
```

Store this on every transaction created from that upload. `source_file` can remain as-is for the raw filename — `upload_batch` is the display/filter field.

**File: `backend/routers/transactions.py`** — Update the source-files endpoint:

```
GET /api/transactions/source-files → GET /api/transactions/batches
```

Returns distinct `upload_batch` values ordered by most recent first.

Update the `source_file` query param to `upload_batch` on the transactions list endpoint.

**Frontend:**

**File: `frontend/src/pages/TransactionsPage.jsx`** — Rename the "Batch" dropdown to use `upload_batch` values. Display shows the human-readable label. Most recent batch at top of dropdown.

**File: `frontend/src/api/client.js`** — Update API calls to use `upload_batch` param instead of `source_file`.

---

## 4. Migration / Backward Compatibility

Since there may already be transactions classified via LLM Inference from previous runs:

- Do NOT delete or reclassify existing LLM-classified transactions — they stay as-is with `method = 'LLM Inference'`
- New classification runs will no longer produce LLM Inference records
- The rule suggestion flow only operates on transactions with `confidence = 'Low'` and `method = 'Unclassified'` (or `gl_code IS NULL`)
- For existing transactions that have `source_file` but no `upload_batch`, backfill `upload_batch` with the `source_file` value so they still appear in the batch filter

---

## 5. Build Order

1. **Batch identifier** — Add `upload_batch` column, update upload endpoint to generate batch labels, update `/source-files` → `/batches` endpoint, update frontend dropdown and API calls. Backfill existing transactions.
2. **Repurpose LLM service** — Create `llm_rule_suggester.py` and `llm_conflict_advisor.py`
3. **Update classification pipeline** — Remove LLM classification step; unmatched transactions get Low/Unclassified/NULL
4. **Add conflict advisory step** — After rule engine, send Medium confidence transactions to conflict advisor
5. **Add API endpoints** — `/suggest-rules`, `/suggest-rules/accept`, `/reclassify`
6. **Update schemas** — RuleSuggestion, SuggestRulesResponse, AcceptSuggestionsRequest
7. **Test backend** — Re-run classification on classify.csv, verify: High confidence transactions classified by rules, Medium flagged with advisory, Low unclassified with no GL code
8. **Build RuleSuggestionsPanel** — New frontend component
9. **Update TransactionsPage** — Unclassified banner, advisory display, updated upload flow
10. **Update stats bar** — Reflect new semantics
11. **End-to-end test** — Upload → classify → review suggestions → approve rules → reclassify → verify improved classification rate
