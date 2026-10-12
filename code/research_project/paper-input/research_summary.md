# Run18 audited factual authoring input



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

## Exact verified facts

{
  "old600_secondary": {
    "initial": 217,
    "blindretry": 240,
    "verifiedretry": 271,
    "lengthmatchedretry": 241
  },
  "reused375_conditional": {
    "primary": {
      "planned": 375,
      "valid": 271,
      "full_only_correct": 30,
      "control_only_correct": 4,
      "difference": 0.0959409594095941,
      "exact_two_sided_McNemar": 6.16488978266716e-06,
      "planned_possible_outcome_bounds_not_CI": [
        -0.208,
        0.3466666666666667
      ]
    },
    "exploratory_SAT_ablation": {
      "planned": 166,
      "valid": 62,
      "full_only_correct": 7,
      "control_only_correct": 11,
      "difference": -0.06451612903225806,
      "exact_two_sided_McNemar": 0.480682373046875,
      "planned_possible_outcome_bounds_not_CI": [
        -0.6506024096385542,
        0.6024096385542169
      ]
    },
    "phase_state_counts": {
      "complete_primary_pair": 271,
      "missing": 1,
      "unattempted_or_interrupted": 103
    },
    "usage": {
      "input": 341390,
      "output": 9473,
      "cache_hit": 1774
    },
    "actual_request_starts": 1820,
    "actual_successful_responses": 1819,
    "scope": "conditional followup on historical initial errors; no new independent cohort; no pooling with600/120",
    "final_input_counts_verified_equal": true,
    "zero_new_model_requests_in_current_Execution": true,
    "probe_usage_is_counted": true,
    "probe_content_not_scored": true,
    "budget": {
      "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
      "control_delta_CNY": "3.105112",
      "attributable_known_successful_control_CNY": "0.745816",
      "residual_control_CNY": "2.359296",
      "known_successful_calls_in_interval": 1791,
      "reserved_delta": 1792,
      "settled_delta": 1792,
      "global_unknown_delta": 1,
      "global_unknown_before": 13,
      "global_unknown_after": 14,
      "raw_missing_requests_not_assumed_equal_global_unknown": true,
      "no_refund_or_reset": true,
      "globally_known_calls_without_raw_in_interval": 0,
      "late_global_usage_promoted_to_scientific_success": false,
      "selected_after_path": "evidence/tokenmatched-followup-20261008/process/tokenmatched-followup-20261008/full_followup-budget-settled.json",
      "selected_after_sha256": "a67aaf7ae68ccf33ae9b564a0ba2e1a707e0fb83d0cf11e0cd424f7920cbec39",
      "original_after_path": "evidence/tokenmatched-followup-20261008/process/tokenmatched-followup-20261008/full_followup-budget-after.json",
      "original_after_sha256": "dd20788aaa07fbeca44cca78d87995d60ef44974645483cb3f14536b1fa5e6a8",
      "original_after_had_active_reservations": true
    },
    "outcome": {
      "selected": 375,
      "durably_recorded_processed": 272,
      "unattempted_or_interrupted": 103,
      "declared_status": "STOPPED_PARTIAL",
      "declared_elapsed_seconds": 3114.184834600019,
      "exit_code": 0,
      "outer_elapsed_seconds": 3114.465533200011,
      "outer_elapsed_includes_import_and_teardown": true
    },
    "source_sha256": {
      "cases.json": "fec6c2a421ac979efa62cf45efdc87d21d0cbd9032bbdb9d4a26f8f20bd92c3d",
      "calls.jsonl": "13bd372c94cca03988be681161a210856dd1ea23e023cb6a9dd7648b925b9a3e",
      "model_calls.jsonl": "44a2e139493da2e96c5bf3e9d87cc36eddf824c134d1ac9f9f1638fe6bd7580b",
      "full_followup-result.json": "b50c44576f4e745a48211633acdea0aca677fe8bfb985130a273214a4f69e5a5",
      "full_followup-rows.json": "8ecfc4cf915cfe34702aa914066dcb7ceadc4af8a63554030bb531cf65705c2d",
      "full_followup-budget-before.json": "267459869a5673cd8fef26b2b4bf3fd9b6302a8a4036930c834586ae6cc400d3",
      "full_followup-budget-after.json": "dd20788aaa07fbeca44cca78d87995d60ef44974645483cb3f14536b1fa5e6a8",
      "full_followup-process-result.json": "f72f3f6a42a3cef81a9fedb5f59680315bf2136ac9975c9f432842db29e9ccee",
      "calibration_only-budget-before.json": "7dd13930ff0d203edacc6ede97a5ea4db4b805773a61fe9052c1398e05bbc741",
      "calibration_only-budget-after.json": "267459869a5673cd8fef26b2b4bf3fd9b6302a8a4036930c834586ae6cc400d3",
      "calibration_only-result.json": "912dc581b6e599f8f11e5059e33a8c4985b1f0d24d0bc23b4aceb77cbc0e2e13",
      "calibration_only-process-result.json": "bc08fb70cc1d0b90b1ddf3d250a30d10ae26b301700b29dd04a32c24d1385505",
      "full_followup-budget-settled.json": "a67aaf7ae68ccf33ae9b564a0ba2e1a707e0fb83d0cf11e0cd424f7920cbec39",
      "full_followup-budget-settled-receipt.json": "1d106749aa9447efd160f2661b550add763668ce27aded3f700b78f7518572cc"
    },
    "whole_study_resource_facts": {
      "control_delta_CNY": "3.117860",
      "resource_segments": [
        {
          "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
          "control_delta_CNY": "0.012748",
          "attributable_known_successful_control_CNY": "0.012748",
          "residual_control_CNY": "0",
          "known_successful_calls_in_interval": 28,
          "reserved_delta": 28,
          "settled_delta": 28,
          "global_unknown_delta": 0,
          "global_unknown_before": 13,
          "global_unknown_after": 13,
          "raw_missing_requests_not_assumed_equal_global_unknown": true,
          "no_refund_or_reset": true
        },
        {
          "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
          "control_delta_CNY": "3.105112",
          "attributable_known_successful_control_CNY": "0.745816",
          "residual_control_CNY": "2.359296",
          "known_successful_calls_in_interval": 1791,
          "reserved_delta": 1792,
          "settled_delta": 1792,
          "global_unknown_delta": 1,
          "global_unknown_before": 13,
          "global_unknown_after": 14,
          "raw_missing_requests_not_assumed_equal_global_unknown": true,
          "no_refund_or_reset": true,
          "globally_known_calls_without_raw_in_interval": 0,
          "late_global_usage_promoted_to_scientific_success": false,
          "selected_after_path": "evidence/tokenmatched-followup-20261008/process/tokenmatched-followup-20261008/full_followup-budget-settled.json",
          "selected_after_sha256": "a67aaf7ae68ccf33ae9b564a0ba2e1a707e0fb83d0cf11e0cd424f7920cbec39",
          "original_after_path": "evidence/tokenmatched-followup-20261008/process/tokenmatched-followup-20261008/full_followup-budget-after.json",
          "original_after_sha256": "dd20788aaa07fbeca44cca78d87995d60ef44974645483cb3f14536b1fa5e6a8",
          "original_after_had_active_reservations": true
        }
      ],
      "actual_request_starts": 1820,
      "actual_successful_responses": 1819,
      "pilot_requests_already_in_shared_raw_journal": 28,
      "pilot_counted_once": true,
      "pilot_independent_audit_sha256": "a8069e6b60927018f5848724d8b4bd4610662468def7e0a2ef66faadb31c7bac",
      "budget_is_conservative_control_accounting_not_supplier_invoice": true
    },
    "posthoc_description": {
      "primary_order_groups": {
        "full> neutral": {
          "planned": 188,
          "valid": 137,
          "missing": 51,
          "full_correct": 24,
          "other_correct": 8,
          "full_only_correct": 16,
          "other_only_correct": 0,
          "both_correct": 8,
          "both_wrong": 113,
          "conditional_difference": 0.11678832116788321
        },
        "neutral> full": {
          "planned": 187,
          "valid": 134,
          "missing": 53,
          "full_correct": 24,
          "other_correct": 14,
          "full_only_correct": 14,
          "other_only_correct": 4,
          "both_correct": 10,
          "both_wrong": 106,
          "conditional_difference": 0.07462686567164178
        }
      },
      "SAT_full_permutation_groups": {
        "full> neutral> coarse": {
          "planned": 28,
          "valid": 11,
          "missing": 17,
          "full_correct": 3,
          "other_correct": 3,
          "full_only_correct": 1,
          "other_only_correct": 1,
          "both_correct": 2,
          "both_wrong": 7,
          "conditional_difference": 0.0
        },
        "full> coarse> neutral": {
          "planned": 28,
          "valid": 11,
          "missing": 17,
          "full_correct": 2,
          "other_correct": 2,
          "full_only_correct": 2,
          "other_only_correct": 2,
          "both_correct": 0,
          "both_wrong": 7,
          "conditional_difference": 0.0
        },
        "neutral> full> coarse": {
          "planned": 28,
          "valid": 10,
          "missing": 18,
          "full_correct": 3,
          "other_correct": 3,
          "full_only_correct": 2,
          "other_only_correct": 2,
          "both_correct": 1,
          "both_wrong": 5,
          "conditional_difference": 0.0
        },
        "neutral> coarse> full": {
          "planned": 28,
          "valid": 10,
          "missing": 18,
          "full_correct": 4,
          "other_correct": 6,
          "full_only_correct": 1,
          "other_only_correct": 3,
          "both_correct": 3,
          "both_wrong": 3,
          "conditional_difference": -0.2
        },
        "coarse> full> neutral": {
          "planned": 27,
          "valid": 10,
          "missing": 17,
          "full_correct": 2,
          "other_correct": 3,
          "full_only_correct": 1,
          "other_only_correct": 2,
          "both_correct": 1,
          "both_wrong": 6,
          "conditional_difference": -0.1
        },
        "coarse> neutral> full": {
          "planned": 27,
          "valid": 10,
          "missing": 17,
          "full_correct": 2,
          "other_correct": 3,
          "full_only_correct": 0,
          "other_only_correct": 1,
          "both_correct": 2,
          "both_wrong": 7,
          "conditional_difference": -0.1
        }
      },
      "primary_aggregate": {
        "planned": 375,
        "valid": 271,
        "missing": 104,
        "full_correct": 48,
        "other_correct": 22,
        "full_only_correct": 30,
        "other_only_correct": 4,
        "both_correct": 18,
        "both_wrong": 219
      },
      "SAT_aggregate": {
        "planned": 166,
        "valid": 62,
        "missing": 104,
        "full_correct": 16,
        "other_correct": 20,
        "full_only_correct": 7,
        "other_only_correct": 11,
        "both_correct": 9,
        "both_wrong": 35
      },
      "matched_valid_primary_final_usage_only": {
        "full": {
          "final_calls": 271,
          "input_tokens": 50036,
          "output_tokens": 3455,
          "cache_hit_tokens": 375,
          "latency_seconds_sum": 450.3174945001083,
          "mean_input_tokens": 184.63468634686348,
          "mean_output_tokens": 12.749077490774908,
          "mean_cache_hit_tokens": 1.3837638376383763,
          "mean_latency_seconds_sum": 1.6616881715871155
        },
        "neutral": {
          "final_calls": 271,
          "input_tokens": 50036,
          "output_tokens": 3501,
          "cache_hit_tokens": 375,
          "latency_seconds_sum": 447.25509989997954,
          "mean_input_tokens": 184.63468634686348,
          "mean_output_tokens": 12.918819188191883,
          "mean_cache_hit_tokens": 1.3837638376383763,
          "mean_latency_seconds_sum": 1.6503878225091495
        }
      },
      "per_pair_resource_equality": {
        "output_tokens_unequal_pairs": 25,
        "cache_hit_tokens_unequal_pairs": 0,
        "latency_seconds_unequal_pairs": 271,
        "input_tokens_equal_pairs": 271
      },
      "posthoc_descriptive_only": true,
      "new_order_inferential_test": false,
      "order_causality_claim": false,
      "resource_subset_includes_only542_primary_final_responses": true,
      "resource_subset_excludes_probes_coarse_partial_errors": true,
      "independent_review_sha256": "e5333643625aac60859217a91e92e602f56e4ff2353218fc32bc4852582cb32e",
      "cache_not_a_calibration_target": true,
      "actual_per_pair_cache_inequality_count": 0
    }
  },
  "new240_primary": {
    "primary_overall240": {
      "planned": 240,
      "valid": 237,
      "full_only_correct": 12,
      "control_only_correct": 1,
      "difference": 0.046413502109704644,
      "exact_two_sided_McNemar": 0.00341796875,
      "planned_possible_outcome_bounds_not_CI": [
        0.03333333333333333,
        0.058333333333333334
      ],
      "not_complete": 3
    },
    "primary_correct_counts": {
      "full_correct": 104,
      "neutral_correct": 93
    },
    "initial": {
      "planned": 240,
      "observed": 239,
      "correct": 87,
      "not_observed": 1,
      "possible_full240_accuracy_bounds_not_CI": [
        0.3625,
        0.36666666666666664
      ]
    },
    "conditional_repair": {
      "planned": 152,
      "valid": 150,
      "full_only_correct": 12,
      "control_only_correct": 1,
      "difference": 0.07333333333333333,
      "exact_two_sided_McNemar": 0.00341796875,
      "planned_possible_outcome_bounds_not_CI": [
        0.05921052631578947,
        0.08552631578947369
      ],
      "not_complete": 2
    },
    "exploratory_SAT_ablation": {
      "planned": 57,
      "valid": 56,
      "full_only_correct": 5,
      "control_only_correct": 2,
      "difference": 0.05357142857142857,
      "exact_two_sided_McNemar": 0.453125,
      "planned_possible_outcome_bounds_not_CI": [
        0.03508771929824561,
        0.07017543859649122
      ],
      "not_complete": 1
    },
    "conditional_initial_error_eligibility_unresolved": 1,
    "SAT_eligibility_unresolved_initials": 0,
    "supplementary_primary_paired_bootstrap": {
      "diagnostic_only": 12,
      "comparator_only": 1,
      "complete_pairs": 237,
      "planned_items": 240,
      "missing_items": 3,
      "paired_difference": 0.046413502109704644,
      "ci95": [
        0.016877637130801686,
        0.0759493670886076
      ],
      "method": "supplementary paired percentile bootstrap with linear quantiles",
      "replicates": 10000,
      "seed": 20261008,
      "confidence_level": 0.95,
      "complete_case_conditional": true,
      "uncertainty_scope": "empirical complete-task distribution; no resampling of model generations",
      "full_planned_missing_difference_bounds": [
        0.03333333333333333,
        0.058333333333333334
      ],
      "missing_bounds_are_confidence_intervals": false,
      "missing_mechanism_assumption": "none; not MCAR or MAR",
      "primary_exact_mcnemar_replaced": false
    },
    "bootstrap_scope": "Registered supplementary primary full versus neutral complete pairs only; conditional on retained237 when missing; fixed unstratified empirical task resampling; no SAT CI; no model-generation resampling; exact paired primary test unchanged",
    "usage": {
      "input": 288383,
      "output": 11438,
      "cache_hit": 43120
    },
    "usage_by_request_phase": {
      "initial": {
        "successful_calls": 239,
        "input": 36179,
        "output": 3855
      },
      "probe": {
        "successful_calls": 718,
        "input": 167287,
        "output": 718
      },
      "final": {
        "successful_calls": 357,
        "input": 84917,
        "output": 6865
      }
    },
    "budget": {
      "resource_segments": [
        {
          "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
          "control_delta_CNY": "4.812722",
          "attributable_known_successful_control_CNY": "0.09413",
          "residual_control_CNY": "4.718592",
          "known_successful_calls_in_interval": 178,
          "reserved_delta": 180,
          "settled_delta": 180,
          "global_unknown_delta": 2,
          "global_unknown_before": 14,
          "global_unknown_after": 16,
          "raw_missing_requests_not_assumed_equal_global_unknown": true,
          "no_refund_or_reset": true,
          "globally_known_calls_without_raw_in_interval": 0,
          "late_global_usage_promoted_to_scientific_success": false,
          "selected_after_path": "private-source-sha256:5cff7c2198ecc3d268c940dd268aca2e4a7c7097496a3924c5748cf78d9d5042",
          "selected_after_sha256": "5cff7c2198ecc3d268c940dd268aca2e4a7c7097496a3924c5748cf78d9d5042",
          "original_after_path": "private-source-sha256:5cff7c2198ecc3d268c940dd268aca2e4a7c7097496a3924c5748cf78d9d5042",
          "original_after_sha256": "5cff7c2198ecc3d268c940dd268aca2e4a7c7097496a3924c5748cf78d9d5042",
          "original_after_had_active_reservations": false
        },
        {
          "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
          "control_delta_CNY": "2.554608",
          "attributable_known_successful_control_CNY": "0.195312",
          "residual_control_CNY": "2.359296",
          "known_successful_calls_in_interval": 383,
          "reserved_delta": 384,
          "settled_delta": 384,
          "global_unknown_delta": 1,
          "global_unknown_before": 16,
          "global_unknown_after": 17,
          "raw_missing_requests_not_assumed_equal_global_unknown": true,
          "no_refund_or_reset": true,
          "globally_known_calls_without_raw_in_interval": 0,
          "late_global_usage_promoted_to_scientific_success": false,
          "selected_after_path": "private-source-sha256:5057870eec2b113de278ae411e70b4590e23a50bd112a1637f89fd18ed665b84",
          "selected_after_sha256": "5057870eec2b113de278ae411e70b4590e23a50bd112a1637f89fd18ed665b84",
          "original_after_path": "private-source-sha256:a57382a8d26b58884f618046b5ae9961449a9dd13ba56e596a95f84f2054a564",
          "original_after_sha256": "a57382a8d26b58884f618046b5ae9961449a9dd13ba56e596a95f84f2054a564",
          "original_after_had_active_reservations": true
        },
        {
          "status": "EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION",
          "control_delta_CNY": "0.378828",
          "attributable_known_successful_control_CNY": "0.378828",
          "residual_control_CNY": "0",
          "known_successful_calls_in_interval": 753,
          "reserved_delta": 753,
          "settled_delta": 753,
          "global_unknown_delta": 0,
          "global_unknown_before": 18,
          "global_unknown_after": 18,
          "raw_missing_requests_not_assumed_equal_global_unknown": true,
          "no_refund_or_reset": true,
          "globally_known_calls_without_raw_in_interval": 0,
          "late_global_usage_promoted_to_scientific_success": false,
          "selected_after_path": "private-source-sha256:ba9381c3d4667f22c2cc22d2951a0f9e65e821b2971e5457dda4df33e5fed3e6",
          "selected_after_sha256": "ba9381c3d4667f22c2cc22d2951a0f9e65e821b2971e5457dda4df33e5fed3e6",
          "original_after_path": "private-source-sha256:ba9381c3d4667f22c2cc22d2951a0f9e65e821b2971e5457dda4df33e5fed3e6",
          "original_after_sha256": "ba9381c3d4667f22c2cc22d2951a0f9e65e821b2971e5457dda4df33e5fed3e6",
          "original_after_had_active_reservations": false
        }
      ],
      "segments_counted_once": true,
      "third_segment_control_CNY": "0.378828",
      "original_client_exit_snapshots_preserved": true,
      "budget_is_control_accounting_not_supplier_invoice": true
    },
    "outcome": {
      "declared_status": "ALL_ELIGIBLE_TASKS_PROCESSED",
      "stop_code": null,
      "processed_cases": 135,
      "inner_elapsed_seconds": 1143.6797752999992,
      "budget_snapshot_settled": true,
      "actual_outer_exit_proof": {
        "source": "actual exec session 84656 terminal result",
        "observed_at_utc": "2026-10-09T02:33:21.6201923Z",
        "automatic_restart": false,
        "exit_code": 0,
        "worker_still_running": false,
        "worker_exit_code": 0
      }
    }
  },
  "semi_automated": true,
  "current_Execution_new_solver_requests": 0,
  "scientific_groups_not_pooled": true
}

# Verified related-work positioning, before followup outcomes

Primary methods were read on 2026-10-08. No cited method was run as a comparative baseline. The planned provider-count-matched followup remains separate from the original decoded-length study and reuses its initial errors.

CRITIC uses a tool-interactive verification step to produce critiques and then correct outputs, optionally repeating the cycle. Its algorithm and oracle setting already establish externally assisted repair. The present contribution should therefore be phrased as a narrow, auditable comparison of feedback information under a measured input-count control, rather than the invention of tool-assisted self-correction. CRITIC also discusses latency and prompt sensitivity.

Source: https://arxiv.org/html/2305.11738v4 , method sections 3.2–3.4, Algorithm 1, experimental oracle setting, Appendix A.

SymDiag translates natural-language reasoning into dual symbolic encodings, audits translation consistency, and obtains step-level diagnosis for subsequent repair. The present tasks arrive as exact symbolic inputs and score final JSON answers. They do not evaluate chain-of-thought faithfulness, natural-language translation, or superiority over SymDiag. The SAT condition can test the incremental role of a clause location while retaining the error category; it cannot establish the effect of SymDiag's overall diagnostic pipeline.

Source: https://arxiv.org/html/2608.08786v1 , sections 3.1–3.3 and 6.1.

GraphArena and GrAlgoBench are useful task context. The present generated graphs are neither dataset and offer no external-benchmark result. Keep synthetic tasks, one model alias, disabled thinking, reused cases, padding semantics, calibration overhead, and partial coverage explicit.

Only actual independently audited followup outcomes may fill the results section. A null or adverse followup result must remain visible; do not revise the original primary endpoint or select another round based on significance.
