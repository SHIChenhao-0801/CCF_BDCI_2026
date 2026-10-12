# Supplementary paired percentile bootstrap plan

This is an additional uncertainty description. The primary exact two-sided
paired McNemar test stays the registered primary inferential procedure. Existing
Wilson intervals are marginal single-arm intervals. Missing-outcome bounds are
worst-case sensitivity bounds and are not confidence intervals.

This supplement is post hoc for the old 600-item study and for the reused
375-item followup. It is fixed before the new 240-item holdout's first initial
answer. The old600 results and Reviewer feedback are already known. No full375
accuracy or final outcome content is opened to specify this supplement.

For each cohort separately, independently audited complete paired correctness
outcomes are summarized as b = diagnostic-only correct, w = comparator-only
correct, n = complete paired items. Comparators remain that cohort's registered
primary matched control and exploratory generic retry; their contrasts are not
pooled across cohorts or converted into additional primary claims.

Reconstruct the canonical task-difference list as [1] repeated b times, then [-1]
repeated w times, then [0] repeated n-b-w times. Within each contrast, create a
fresh Python standard-library Random(20261008). Generate exactly 10000 replicates.
Each replicate independently samples n indices with replacement using
Random.randrange(n) and reports the mean paired task difference. Sort those
10000 means. The 95% percentile interval uses probabilities .025 and .975 with
linear interpolation: h=(10000-1)*p, interpolate the neighboring order
statistics at floor(h) and ceil(h). No global RNG is used or advanced, and the
same seed is reset for each cohort and contrast. These are approximate
supplementary paired percentile bootstrap intervals, not BCa, basic, exact,
simultaneous/multiplicity-adjusted, or marginal arm intervals.

If outcomes are missing, the interval conditions on the observed complete pairs.
Display the complete and planned denominators, missing count, and the full-planned
worst-case difference bounds [(b-w-m)/N, (b-w+m)/N] alongside it. Those sensitivity
bounds permit every unobserved paired difference in {-1,0,1}; they do not impute
outcomes. Make no missing-at-random or MCAR assumption. A complete-case bootstrap
does not solve nonrandom missingness, establish population/model generality, or
replace raw response audit. These intervals describe task-resampling uncertainty
under the empirical complete-task distribution; they do not resample model
generations or account for arbitrary task dependence.

Analysis is delayed until each corresponding raw terminal independent audit is
available and root authorizes using it. The helper accepts only an explicit
single-cohort contrast summary, audit identity, and its full-planned denominator.
The old600, reused375 and new240 results are generated separately. No current
full375 statistics are read while preparing or testing the helper.

Before execution the implementation is tested against an independent NumPy
linear quantile calculation, controlled all-zero and all-positive/all-negative
paired differences, deterministic independent reruns, unchanged global RNG,
unchanged caller input, and missing/denominator edge cases. Its implementation
uses only the Python standard library; NumPy is a retained validation reference,
not a runtime dependency. All outputs and provenance remain in this new process
directory. No framework, paper, frozen study, dataset, or API is changed.
