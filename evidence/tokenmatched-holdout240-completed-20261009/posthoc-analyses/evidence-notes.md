# Verified additions for the 9 October paper revision

All computations are offline, using the original three-segment 240-item call journal, frozen dataset, and independently audited per-item classification. `extract.py` also scores all 150 completed retry pairs directly with the frozen deterministic oracle and checks exact agreement with the independent classifications. No new model call or experiment is claimed.

## What the matched-input experiment controls

Both retry arms retain the same initial task and assistant response. The final user message starts with the identical instruction `Reconsider your previous answer and return only the requested final JSON object.` Then `Deterministic checker feedback: ` is followed by compact JSON: the full arm gets the actual checker diagnostic, whereas neutral gets `{}`. Both end with `Inert padding; ignore this line:` followed by repeated ` a` units.

Two zero-padding probes, each with `max_tokens=1`, establish each arm's returned input-token count. The target is the larger count plus 4. The controller updates padding toward that target, with a secant-style interpolation if distinct earlier observations exist and a direct token-count-difference update otherwise. Each arm is limited to 5 probes and padding to 64 units; an identical probe is never resent. Probe outputs are not parsed, scored, or passed to a retry. Only returned `usage.prompt_tokens` are used. Each final answer is generated independently from its original three-message context with `max_tokens=2048`, temperature 0, `thinking` disabled. Both final returned prompt-token counts must equal the same calibration target, or the item is excluded. SAT coarse feedback removes only `clause_index`; its calibration targets the primary pair's fixed target and never changes the full-versus-neutral contrast.

This equalizes returned input counts for retained comparisons, not padding semantics, output length, elapsed time, or hidden compute. The examples and output-token measurement below reduce ambiguity without upgrading this limitation to full compute control.

## Actual output tokens

Among 150 retained independently generated retry pairs, each arm consumes 33,512 input tokens. Full outputs total 2,608 tokens, neutral outputs 2,616. Means are 17.3867 versus 17.4400, paired mean difference -0.0533 tokens, median difference 0, range -4 to +4. For all 58 arithmetic and 56 SAT retry pairs, output counts match exactly within each pair. Output differences occur only in graph pairs. This is a descriptive post-experiment measurement, not a preregistered output-budget control.

An optional post-hoc equal-output subset contains 142 retry pairs with b=9 and c=1; conditioning on output length can select on an outcome-related variable, so this is descriptive sensitivity only and should not replace the primary estimand or be called causal evidence.

## Exact illustrative instance (selected after outcomes, not a benchmark)

`sat-holdout240-easy-35` has six Boolean variables and twelve clauses. The initial answer is `[1,1,1,1,1,1]`. The deterministic checker reports `{"error":"clause_unsatisfied","clause_index":8}`. Clause 8 is `[-5,-6,-3]`, which this assignment makes false. Full feedback returns `[1,1,1,1,1,0]`, which satisfies every clause. Neutral returns the unchanged all-one assignment. Full zero-padding input count is 235 and neutral is 220; full adds 4 units and neutral adds 19, yielding the common input target 239. Both final outputs have 21 tokens. Complete original prompts, requests, results, usage and probe observations are in `exact-prompt-example.json`; no oracle assignment is included in actual model request messages.

## Heterogeneity and limits

Six planned cells have 40 items each. Their exact descriptive comparisons are in `six-cells.tex` and `evidence.json`. No individual cell has an unadjusted exact p below .05; six exploratory comparisons therefore do not support a multiplicity-corrected family-specific claim. SAT easy contributes b=7,c=1 of the aggregate b=12,c=1, suggesting a descriptive concentration. Hard arithmetic has zero correct final answers in either arm across 40 retained items. A directly checked instance `arithmetic-holdout240-hard-21` requires 3905, whereas initial, full and neutral each return 4025. This documents failure to repair with the coarse arithmetic mismatch diagnostic; it does not establish the internal cause of model failure.

The 87 initially correct items contribute shared (correct,correct) outcomes to the 237-item overall comparison and do not trigger calibration or new retries. The 150 independently generated retry pairs are the retained subset of 152 observed initial-error cases. The three missing overall items reflect: unknown/failed neutral final for SAT easy 40; error on graph hard 32 initial; unknown/failed full calibration probe for arithmetic easy 21. These missing states are not incorrect model answers. No such call is retransmitted.

## Actual call phases and calibration overhead

Across three administrative segments there are 1,317 started requests and 1,314 successful responses. Successful calls split into 239 initials, 718 probes, and 357 final retry/ablation responses. Their input tokens are 36,179, 167,287, and 84,917; output tokens are 3,855, 718, and 6,865. Overall successful usage is 288,383 input plus 11,438 output, with cache-hit input 43,120 already included in input. Calibration therefore consumes 58.0086% of observed successful input tokens (167287/288383), a real overhead that must be included in resource reporting. Whole-study accounting includes SAT ablation, partial discarded calls, and calibration, whereas the 33,512-per-arm number covers only primary retained final pairs. These denominators must not be mixed.
