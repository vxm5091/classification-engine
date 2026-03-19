# Implementation Plan: Rule Engine Specificity Fix

## Problem

When multiple rules match a transaction with different GL codes, the engine flags all of them as Medium confidence conflicts. It should first rank rules by specificity and only flag as Medium when the top candidates are equally specific.

**Example:** Amazon Prime transaction matches:
- Rule 43: AMAZON → 6160 (vendor only, specificity = 1)
- Rule A: AMAZON + AMAZON-PRM → 6200 (vendor + service, specificity = 2)

Currently: Medium confidence, flagged as conflict.
Expected: High confidence, GL 6200 — Rule A is strictly more specific.

## Fix

**File: `backend/services/rule_engine.py`**

Replace the conflict resolution logic in the multi-match branch. Instead of immediately flagging any GL code disagreement as a conflict, score and rank rules first.

### Specificity Scoring

Each matching rule gets a specificity score:

```python
def score_rule(rule):
    score = 0
    if rule.vendor_id:
        score += 1
    if rule.service_id:
        score += 1
    if rule.amount_min is not None or rule.amount_max is not None:
        score += 1
    if rule.time_of_month_start is not None or rule.time_of_month_end is not None:
        score += 1
    return score
```

### Revised Conflict Resolution

```python
# After collecting all matching_rules with different GL codes:

# 1. Score each rule
scored = [(score_rule(r), r) for r in matching_rules]
scored.sort(key=lambda x: x[0], reverse=True)

max_score = scored[0][0]

# 2. Get all rules at the highest specificity level
top_rules = [r for s, r in scored if s == max_score]

# 3. Check if top-tier rules agree on GL code
top_gl_codes = set(r.gl_code for r in top_rules)

if len(top_gl_codes) == 1:
    # Single winner at highest specificity — High confidence
    rule = top_rules[0]
    return {
        'gl_code': rule.gl_code,
        'confidence': 'High',
        'method': 'Rule Match',
        'rule_id': rule.rule_id,
        'reasoning': f'Rule R-{rule.rule_id}: Matched as most specific rule '
                     f'(specificity {max_score}) among {len(matching_rules)} candidates. '
                     f'{format_rule_criteria(rule)} → GL {rule.gl_code}'
    }
else:
    # Genuine conflict — equally specific rules disagree
    conflict_detail = ', '.join(
        [f'R-{r.rule_id}→GL {r.gl_code} (specificity {score_rule(r)})' for r in top_rules]
    )
    return {
        'gl_code': top_rules[0].gl_code,  # Best guess from first top rule
        'confidence': 'Medium',
        'method': 'Rule Match',
        'rule_id': top_rules[0].rule_id,
        'reasoning': f'RULE CONFLICT: {len(top_rules)} rules at same specificity level '
                     f'({max_score}) disagree: {conflict_detail}. Review recommended.',
        'review_status': 'Flagged'
    }
```

### Full Decision Tree (for clarity)

```
Multiple rules match:
├── All agree on GL code → High confidence (unchanged)
├── Disagree on GL code:
│   ├── Score all rules by specificity
│   ├── Top-scored rules all agree → High confidence (most specific wins)
│   └── Top-scored rules disagree → Medium confidence, flagged (genuine conflict)
```

## Testing

After the fix, re-upload `test_curveball.csv`. Expected changes:

| Transaction | Before | After |
|------------|--------|-------|
| Amazon Prime $16.09 | Medium / Flagged / conflict | **High / Unreviewed / GL 6200** (Rule A: AMAZON+AMAZON-PRM wins over Rule 43: AMAZON-only) |
| Microsoft $14.99 | Medium / Flagged / conflict | **High / Unreviewed / GL 6160** (Rule B: MSFT+amount wins over Rule 88: MSFT-only) |
| All other rows | No change | No change |

## Scope

This is a single-file fix in `rule_engine.py`. No schema changes. No API changes. No frontend changes. The reasoning string will be slightly different for specificity-resolved matches vs clean single matches, but the confidence and method fields are unchanged.
