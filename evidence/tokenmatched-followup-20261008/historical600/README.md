# Four-stage reasoning replication: public zero-API reconstruction

This bundle reconstructs the fixed 600-item study from retained raw request/response journals. It contains 592 fully observed paired items and 8 declared missing items. The original strict 600-item execution and its first continuation remain FAILED. The final resume terminated with `COMPLETED_WITH_DECLARED_MISSING`; it did not turn the original registration into an unchanged complete study.

From this directory, with Python 3.12, run:

```text
python -B -X utf8 replay.py
```

The command uses only the Python standard library, reads only files inside this bundle, and writes `replay-result.json`. It needs no API key, environment configuration, model, Reviewer, network access, JiuwenSwarm installation or TeX compiler. It works after moving the entire directory elsewhere. Optional checks run with:

```text
python -B -X utf8 -m unittest -v test_replay.py
```

The replay checks every immutable file against `public-manifest.json`, every exact copy against `copy-identity.json`, all 600 arithmetic/SAT/graph oracles, 156 prior-item exclusions, each attempted request template, within-item arm order, absence of reissued started/error/observed request keys, response-ID uniqueness and prior disjointness, actual response-to-usage journal matching, shared initial-answer reuse, independently rescored answers, the six generation-size cells, exact paired McNemar statistics and Wilson intervals. It compares independently rebuilt rows and statistics with the archived producer outputs and independent audit.

The four correct counts are initial 217, generic retry 240, diagnostic retry 271, and the character/UTF-8 matched retry 241, each over 592 observed complete items. The primary paired contrast is 32 diagnostic-only versus 2 control-only, difference `30/592`, exact two-sided p `6.938353180885315e-08`. The secondary generic contrast is exploratory. Matching decoded characters and UTF-8 bytes does not imply matching model prompt tokens; the retained prompt-token mismatches are rebuilt from raw usage.

All 8 missing items remain visible. Five historical requests ended with client error records and three retain a started-only unknown disposition; none is silently scored incorrect, deleted from the planned denominator, retried or replaced. The replay enumerates all 45 distinct missing-discordance allocations for each comparison. Primary full-600 paired difference bounds are `22/600` to `38/600`; possible p-values range from `4.1109160520136356e-10` to `0.0009406740282429382`. These are worst-case bounds, not confidence intervals or an imputed dataset, and assume no missing-at-random mechanism.

Scientific inference uses 1,717 successful calls supporting the 592 complete pairs. Resource accounting uses all 1,721 successful calls, including four successful partial-item responses that contribute cost but no complete paired item. Their four-arm outcomes are not fabricated. All-successful usage is 325,449 input, 31,574 output, and 36,480 cache-hit tokens; scientific-pair usage is 324,782 input, 31,504 output, and 36,480 cache-hit tokens. The eight scientific missing items, the five error plus three started-only client records, and the seven added global unknown accounting entries are distinct quantities; this bundle does not infer an unproved request-to-charge mapping or refund.

Only sealed accounting snapshots are read. The Oct8 resume retains 13 historical global unknown entries, adds no new unknown entry, settles all new reservations, and increases conservative control charge by CNY 0.271436. Known-response totals across the four stages are CNY 0.903490 at the conservative input/output control rates, or CNY 0.83198920 using the retained cache-aware peak-rate estimate. These are retained-rate calculations and conservative control bookkeeping, not a vendor invoice. No live ledger is opened or reset.

`history/` contains selected original bytes from the initial attempt, first continuation, three-worker completion amendment and two-worker Oct8 resume. Original failed records and partial-item responses are included. `source/frozen_auditors/` retains the four original independent auditors; `source/frozen_callers/` retains selected registered reference sources and plans. They are archived review material, not this bundle's execution entry. The portable entry imports only exact scientific function segments in `audit/`, with their original-source and segment hashes in `copy-identity.json`. The legacy host/model caller is omitted while its scoring segments and original-source receipt are retained.

Original registrations contain host-specific protected-file indices. `registrations.json` explicitly projects their original SHA256, registration times and relative frozen-file hashes; it is not a replacement original registration. The public resume amendment and accounting projection retain the original record hashes while omitting host operational details. No private configuration, Reviewer access material, account email, environment, venv/cache, current live control files, or unfinished new followup experiment is included. Every entry marked `EXACT_RAW_COPY` matches its source SHA256; derived projections and function modules are marked separately.

At export time the older main `paper/paper.pdf` has not been promoted to the newer focused paper. This evidence package supports the independently checked 592-item study and does not claim a new complete Agent workflow, paper promotion, Reviewer score or contest upload. The currently running followup is separate and is not part of this frozen bundle.
