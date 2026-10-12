# Frozen-response reanalysis for an auditable one-shot repair paper

This run is an offline reanalysis of responses already generated and frozen before run15. It is not a new solver evaluation, new benchmark or additional independent sample. Human preparation supplies the topic, frozen protocol/data/code and curated sources; the actual JiuwenSwarm Manager must perform design, prepared-code implementation, deterministic execution, reflection and ICLR reporting. Do not claim autonomous topic discovery or experiment programming.

Research question: among synthetic tasks with a checker-rejected initial answer, does one isolated retry with a deterministic error diagnostic outperform one isolated retry with neutral text matched in decoded characters and UTF-8 bytes? The prespecified primary comparison is diagnostic versus decoded-length control. Diagnostic versus generic reconsideration is secondary/exploratory. The shared-initial selective-retry policy retains initially correct answers; monotonic improvement relative to initial is built into this policy and is not evidence of intrinsic self-correction.

The fixed original plan is600 generated tasks:100 per arithmetic/SAT/graph easy/hard cell. Frozen complete cases are592, with8 scientific missing items. Observed counts initial/generic/diagnostic/length are217/240/271/241. Primary discordance32/2, difference5.0676percentage points, exact two-sided McNemar p=6.938353180885315e-08. Secondary34/3, difference5.2365points,p=1.233129296451807e-07. All statistics were computed after all600 items received terminal scientific disposition. Continue and stopping decisions did not depend on efficacy. Original strict600 and first continuation remain FAILED; prior completion remains STOPPED_FOR_BOARDING. The final dataset belongs to disclosed operational amendments, including concurrency and the flight interruption, not an unchanged preregistered600 execution.

Complete cell denominators arithmetic easy/hard=98/99;graph easy/hard=97/99;SAT easy/hard=99/100. Full count strings initial/generic/diagnostic/length:arithmetic easy64/65/65/64,arithmetic hard4/4/5/4,graph easy58/73/79/73,graph hard58/62/68/63,SAT easy28/31/47/32,SAT hard5/5/7/5. Preserve poor hard-case results and schema failures. Returned malformed answers count as wrong, never as transport-missing.

Exactly375 initial errors received three isolated retries, each using the original prompt and shared initial answer only. There is no chained retry history between arms. Diagnostics identify a constraint violation, not a correct answer. The checker has oracle-level access: arithmetic uses exact operations,SAT checks clauses,graph checks cost and shortestness. State that this is external verification and an oracle-selected repair policy; checker availability and computation limit deployment relevance. The verifier itself can solve these toy tasks, so this is not a claim that the feedback workflow is the most efficient solver.

Scientific solver configuration is one DeepSeek model ID deepseek-flash,temperature0,thinking disabled,max_tokens2048,nonstreaming,automatic retries0. The research Agent will make separate new authoring/design/manager calls; those must never be counted as additional solver samples. Actual returned prompt lengths for375 initial-error pairs show diagnostic minus length control3to10tokens,mean6.8826666667,total2581. The control is equal in decoded characters/UTF-8 bytes,not equal in tokenizer length. Language/content naturalness and slight token inequality remain confounds. Both extra-call controls are informative, but causal attribution solely to error information is not established.

Missing policy: five historical raw transport errors plus three started-without-terminal requests exclude the whole item from all scientific arms. None was resent or partially completed. The global monetary ledger has13 historical unknown calls, seven added during earlier research; this differs from eight missing items. Missingness may bias the complete-case comparison; do not assumeMCAR. Enumerate all possible outcomes of the8 missing pairs: primary full600 difference3.6667to6.3333points,p range4.1109160520136356e-10to0.0009406740282429382. These are possible-outcome bounds,not imputations or confidence intervals.

Historical evidence remains separate: the earlier registered120-item four-arm study found51/54/60/57 correct,primary discordance5/2,p=.453125 andsecondary7/1,p=.0703125. Report this inconclusive prior result as separate context; no pooling,discarding or favorable-round selection. The old24 engineering set is not newly evaluated in this run and is not a sealed holdout for this paper. Do not import the older manuscript's24/120 figures as current600 data.

Resources: all four research stages have1721 unique successful responses,including4 successful responses belonging to missing items. Complete-case scientific use is1717=592+3×375. All-response usage325449input,31574output,36480cache-hit; scientific use324782input,31504output,36480cache-hit. Cache-hit is a subset of input. All failed/pending usage remains unknown. New run15 Execution uses zero new model calls and must not append historical response usage to run15's Manager ledger. Historical costs/timings belong to solver evidence and current Manager/Design/Reflection/Reporting costs are separate.

Runtime: original recorded guard elapsed2034.625s,first continuation238.125s,8October resumption357.5610653s. Historical completion has no elapsed field:null. Two-worker resumption sums686.5508246s of successful per-call latencies but has357.5610653s elapsed. Across all stages the request-start span122129.878571s includes the overnight flight pause. Do not invent an all-stage active runtime or confuse latency-workload totals with elapsed wall time.

PreparedCode public files are exactlyrun.py,dataset.json,manifest.json,PROTOCOL.md. Dataset embeds600 original tasks,3455 raw journal events,1721 resource events and provenance hashes. Manifest binds source,data andprotocol. Independent pure scoring/request validation/statistics functions are reused inrun.py; it contains no model/network caller. The resulting statistics/resources/missing sensitivity must exactly match the frozen independent final audit. Historical metadata is descriptive and not a new current model-call event.

Commands arePython3.12stdlib only. PreparedCode smoke calls `python run.py --method paired_study --smoke-test --output <smoke_metrics> --usage-ledger <manager_ledger> --task-id <task> --node-ref <run>`; it fully checks/replays historical evidence and emits methodpaired_study,statuscompleted,smoke_testtrue,model_call_count0. Actual ExperimentExecution appends `--output <metrics>` withoutsmoke; this performs the same real offline computation and emitssmoke_testfalse,model_call_count0. `--run-eval` is an offline-only alias,never a network trigger. The ledger argument is accepted for the existing framework contract but never written by this runner. After PreparedCode/Execution,actual Reflection must discuss protocol amendments,missingness,oracle access,token confound and hard failures;then Reporting writes and compiles a concise EnglishICLRshort paper.

APG is separate: it checks a nonemptyPDF,successfulReporting status,safe declared artifact paths,aggregable model-call ledger andAUXcitation/bibcite keys. It does not check semantic answer correctness,scientific truth,missing-result completeness or whether citation content supports a claim. run15's APG ledger should contain only actual new Agent authoring calls,not duplicated historical solver usage.

Use only these supplied primary-source references where semantically relevant; avoid claims beyond their recorded abstract-level scope. Metadata was checked in the earlier local source preparation. Feedback inSelf-Refine is model-generated;Huang distinguishes intrinsic from externally aided correction;ReAct andReflexion supply related tool/feedback context,not evidence for this experiment's outcome. Do not add references to satisfy a count.

```bibtex
@article{madaan2023selfrefine,
  title={Self-Refine: Iterative Refinement with Self-Feedback},
  author={Madaan, Aman and Tandon, Niket and Gupta, Prakhar and Hallinan, Skyler and Gao, Luyu and Wiegreffe, Sarah and Alon, Uri and Dziri, Nouha and Prabhumoye, Shrimai and Yang, Yiming and Gupta, Shashank and Majumder, Bodhisattwa Prasad and Hermann, Katherine and Welleck, Sean and Yazdanbakhsh, Amir and Clark, Peter},
  year={2023},journal={arXiv preprint arXiv:2303.17651},url={https://arxiv.org/abs/2303.17651}
}
@article{huang2023selfcorrect,
  title={Large Language Models Cannot Self-Correct Reasoning Yet},
  author={Huang, Jie and Chen, Xinyun and Mishra, Swaroop and Zheng, Huaixiu Steven and Yu, Adams Wei and Song, Xinying and Zhou, Denny},
  year={2023},journal={arXiv preprint arXiv:2310.01798},url={https://arxiv.org/abs/2310.01798}
}
@article{yao2022react,
  title={{ReAct}: Synergizing Reasoning and Acting in Language Models},
  author={Yao, Shunyu and Zhao, Jeffrey and Yu, Dian and Du, Nan and Shafran, Izhak and Narasimhan, Karthik and Cao, Yuan},
  year={2022},journal={arXiv preprint arXiv:2210.03629},url={https://arxiv.org/abs/2210.03629}
}
@article{shinn2023reflexion,
  title={Reflexion: Language Agents with Verbal Reinforcement Learning},
  author={Shinn, Noah and Cassano, Federico and Berman, Edward and Gopinath, Ashwin and Narasimhan, Karthik and Yao, Shunyu},
  year={2023},journal={arXiv preprint arXiv:2303.11366},url={https://arxiv.org/abs/2303.11366}
}
```


# Separate conditional followup, preregistered before outcomes

The original600 study remains intact:600 planned,592 complete,8 missing; decoded-length control is not token matched. Current Execution is a reproducible offline reanalysis, not a new solver experiment. Preserve all original response identities and no pooling with120 or24.

The followup uses the375 initially incorrect cases from those592 complete items. These are reused historical initial errors, not375 new independent samples and not an overall592 accuracy denominator. Primary comparison is full original checker feedback versus the neutral{} placeholder. Neutral{} is a container without task semantics, not a semantic-schema-equivalent control. SAT location ablation is exploratory and restricted to166cases whose original checker feedback includes clause_index; retain error category and remove only clause_index. Keep primary375 and SAT166 planned denominators distinct and disclose valid, missing, local stop and unattempted coverage.

Calibration used returned provider prompt_tokens, at most five distinct max_tokens1 probes per arm, target max(initial full/neutral counts)+4 and bounded inert padding. No probe correctness or effect size guided admission or calibration. Final retries use2048 output limit,temperature0,thinkingdisabled,the same3messages and exact frozen order; include a pair only when actual final prompt_tokens match. Report calibration costs and any final count drift. Do not claim a frozen tokenizer or immutable vendor model weights. The six-case calibration pilot is feasibility evidence only; its probes are a subset of the same raw journal and usage, never added a second time.

No positive outcome is required. Preserve null, adverse, incomplete and missing outcomes. Missing-outcome ranges use each planned denominator and are not confidence intervals or imputed datasets. Avoid intrinsic-self-correction claims; these exact symbolic tasks use an externally supplied oracle checker.

SDK PreparedCode copies only run.py,dataset.json,manifest.json,PROTOCOL.md. Therefore frozen600 and followup raw requests, successful usage ledger and terminal independent audit are embedded in dataset.json; pure replay functions are embedded in run.py. Bibliography files are separate staged paper inputs, not extra generated-code dependencies.

Design related_report_ids must be[] before any real previous module report exists. Integrity criteria use counts32/2 and the exact30/592 comparison (or abs(metric-30/592)<1e-12), never rounded0.050676 equality. Followup values are computed only after terminal raw audit; they are not positivity criteria. Reflection must genuinely check method, missingness, actual output-token confounds, prior120 separation, source citations and negative results. Use actual report IDs in related_report_ids and do not force acceptance or fabricate Reflection.

Current official paper length is not capped at six pages. Keep necessary method details; any short-paper word target is an editorial preference, not an eligibility gate.


# New independent holdout, approved before reading current375 efficacy

Run16 primary evidence is the separately frozen240-case holdout: six cells40each, registered generator seed batches20261024–20261030 (seven batches; bounded search limit64), canonical instances/prompts excluded against36+120+600=756existing tasks. One new initial response is generated per attempted task. A correct initial response is shared by the full and neutral arms and counted once as a model call. An incorrect initial response supplies the same original checker feedback and history to isolated, vendor-count-calibrated retries. SAT location ablation eligibility depends on an observed incorrect initial with clause_index; unobserved SAT initials have unresolved eligibility. Keep the separate independent_new_holdout bundle and its source hashes; never overwrite600or375data. The new240 result is the primary new evidence,375is a conditional reused-error followup,600is the original decoded-length experiment and120is separate historical context. Actual complete pairs determine the complete-case comparison; the original240 denominator determines worst-case missing-outcome bounds. Terminal raw audit and settled resource evidence are required before this Agent input becomes ready.


# Existing host table/figure identity
The fixed host-rendered baseline/generic/verifier/lengthmatched table and figure use old600 scalar metrics with592complete cases. They belong only to the retained decoded-length study and should appear as secondary/appendix context with that label. They are not375followup or new240results. Preserve those original scalar values. The new240primary table must be newly written from independent_new_holdout's audited nested fields, with its real observed/complete/missing denominators. Model-authored TeX tables may present those exact host facts; do not replace old scalar values to silently switch experiments.

# Administrative continuation after the first holdout result

The first holdout segment retained32 valid pairs and208 missing outcomes. After observing that result, root allocated an additional control-accounting ceiling of2.820774CNY while protecting8CNY for the subsequent Agent. This resource amendment was not fixed before the first segment's outcomes. It introduced no samples or altered endpoints, model settings, calibration, order or scoring. Continuation admitted only the206 original tasks with no durable raw request event at all. None of the34 previously started tasks, including the two failed requests, was resent. Both segments and all missing outcomes remain in the original fixed240 population. Disclose the after-result budget decision rather than calling the entire resource schedule preregistered. Admission and termination use the assigned budget and request policy, never significance or repair efficacy.

The continuation's combined raw evidence is an explicitly derived concatenation of original and new journals. Resource ledgers stay separate and are aggregated once. Preserve original client-exit budget snapshots containing active reservations; use an additional root-issued settled snapshot and receipt for terminal finance. A process exit is not proof of settled network requests, and late global settlement cannot manufacture a missing scientific response.

# Optional descriptive and uncertainty supplements

The375 descriptive supplement is post hoc and independently reconstructed from raw final responses. Its absolute correct counts, order groups and matched-valid-final resource subset remain descriptive. Different order groups have different composition and missingness; do not infer order causality or add subgroup significance tests. The542 valid primary final calls exclude calibration probes, coarse finals, partial cases and errors; they do not replace whole-study resource accounting. Actual prompt tokens are equal in271 pairs. Actual cache tokens also happen to be equal in those pairs, but cache was not a calibration target. Output tokens differ in25 pairs and observed latency differs in271 pairs. The reviewed SAT absolute counts16 versus20 among62 valid pairs describe the exploratory location ablation, including its adverse direction.

The supplementary primary240 paired percentile bootstrap was registered before any holdout initial request. Use exactly10000 replicates, fresh Random(20261008), the canonical difference vector [1]*b+[-1]*w+[0]*(n-b-w), n draws with replacement, and linear .025/.975 quantiles. It is an unstratified empirical task bootstrap and is conditional on complete pairs when outcomes are missing. Show the planned240 missing-outcome bounds alongside it, with no MCAR/MAR claim. It resamples tasks, not model generations, and does not replace the primary exact McNemar test. No SAT-ablation bootstrap interval is added. Any old600 bootstrap interval is explicitly a separate post hoc supplement to that secondary study.

# System and automation scope

The approved Artifact Provenance Gate remains a deterministic contribution inside JiuwenSwarm: artifact/report/path/ledger/AUX citation checks. It establishes artifact integrity, not scientific answer verification. PreparedCode uses exact four-file copying and a real zero-model smoke; the current worker and writer preserve runtime identities and bounded evidence summaries. Separate oracle/raw-response audits support scientific statistics. Human/host-provided protocol and frozen responses make this a semi-automated research workflow. Current Execution issues zero new solver requests, while genuine Manager module calls consume newly recorded resources. A successful workflow, Reflection outcome, PDF compilation, Reviewer correspondence or submission must be established by actual later evidence rather than inferred from this input bundle.

The new240 portable replay contract is now implemented from the independent auditor; actual terminal raw data and budgets remain unavailable. Group-specific final-count matching and distinct denominator fields are recomputed from raw; a supplied terminal summary cannot replace independent computation.


The supplementary paired bootstrap plan was registered at 2026-10-08T11:22:04.245533+00:00 while holdout model requests were zero. Its numerical implementation was independently checked against NumPy linear quantiles (30 checks, maximum absolute error0). This is supplementary uncertainty analysis, not a change to the registered primary exact paired test. Add its independently audit-bound primary240 paired interval only when actual terminal data exist; show missing-outcome bounds alongside it and label those bounds separately from confidence intervals. Registration/proof sources: process/paired-bootstrap-supplement-20261008/registration.json and numpy-reference-proof.json.


# Third administrative segment, decided after prior observed results
The fixed original 240 population is replayed from three separate retained acquisition segments.
After observing prior results, the operator authorized completion of exactly 135 never-started items.
The 105 previously started items, including retained failures, were never retransmitted.
Third segment: 753 starts, 753 successful responses, no new unknown calls, 0.378828 CNY conservative control cost.
Whole science: 1317 starts, 1314 successful responses; these are historical input usage, not new Agent calls.
This resource decision was not fully preregistered. Original hypothesis, task order, oracle, calibration,
endpoint, fixed denominator 240 and original bootstrap registration remain unchanged.
Primary: 237 complete, 3 missing; full 104/237, neutral 93/237; discordance 12/1, exact p=0.00341796875.
Paired difference 11/237; full-240 possible-outcome bounds 8/240 to 14/240, not confidence intervals.
Conditional repair: 150/152 observed initial-error cases, one unresolved initial eligibility.
SAT location ablation: 56/57, discordance 5/2, p=0.453125; no positive ablation finding.
Old600, reused375, old120 and this fixed240 remain separate populations. Current Execution makes zero solver requests.
