# Protocol-specific scope clarification after peer review

This narrows the use of the registered supplement to the actual registered
comparisons. It changes no random seed, replicate count, interpolation, endpoint,
resampling algorithm, missingness treatment, or primary inference. Original
PLAN.md, registration.json, implementation, tests and metadata remain preserved.

The new240 protocol has no generic-retry arm. Its supplement input must contain
only its actual primary matched-control contrast. The generic-retry contrast in
the initial null-filled analysis-input-template.json is inapplicable to new240;
that original preparation template is retained for the record and is superseded
by new240-primary-input-template.json. Old600/reused375 may describe a generic
contrast only when it actually exists in the corresponding frozen raw audit.

Each analyze_cohort summary has one n and planned_n shared by all its contrasts.
Use that interface only for contrasts with exactly the same audited valid-pair
mask and planned-task mask, not merely equal item counts. The helper cannot
establish mask equality from b/w/n and a caller-supplied audit receipt. Confirm
those masks in the independent raw audit. If masks differ, do not combine their
contrasts in one input. The 600/375/240 planned denominators are fixed by the
helper's cohort names; it does not cover analyses with a different conditional
planned denominator.

In particular, the SAT-clause ablation has its own conditional denominator and
is outside this helper's registered three-cohort use. Do not use n240 or any
whole-study denominator for that ablation. This supplement adds no SAT-clause
bootstrap analysis.

The procedure is an unstratified bootstrap of the pooled empirical task
differences inside a single cohort. It does not preserve the fixed counts of
the six family/size cells in every resample and does not address task dependence.
This is a methodological limitation to state beside the supplementary CI.
Nothing is pooled across old600/reused375/new240.

Peer read-only review found no material P0/P1 implementation or statistical
semantic defect in the paired resampling, seed reset, endpoints, denominators
or missing bounds. These scope points must remain visible in the final facts.
No real current375/current240 result was opened for this clarification.
