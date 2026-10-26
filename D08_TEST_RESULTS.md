# D08 — Resultados de testes

## Defeito reproduzido antes da correção

Comando: `python -B candidate/tests/test_d08_auth.py AuthTests.test_late_coverage_401_does_not_discard_new_key`.

Baseline publicada bd8477e429fa8408c11b4b2d2b551666a2359a97. Resultado inicial: 1 FAIL, exit 1, 0,002 s. Evidência: `AssertionError: 3 != 2 : A stale 401 must not trigger a third authentication`. Um GET antigo retido por barreira sintética respondeu 401 após outra requisição renovar a chave por expiração. O cliente invalidou a chave nova e emitiu um terceiro auth desnecessário. Nenhuma chamada real foi feita; transporte injetado, DNS/socket/SQLite bloqueados no processo de teste.

Esse defeito de concorrência não comprova a causa histórica do HTTP 401 Santander nem da divergência de Item Itaú.

## Defeito de interface reproduzido

Antes de corrigir app.js: `node --test candidate/tests/test_d08_ui.mjs`: 3 PASS / 1 FAIL, exit 1. A resposta HTTP 502 com run.error_code=AUTH_FAILED resultou em Error.code undefined. Assert preservado: undefined != AUTH_FAILED. Os demais três controles passaram. O helper novo ainda não estava conectado à interface. Nenhuma chamada de rede: fetch falso.

## Open Finance / workers / SQLite / diagnostics

Comando: `C:\Users\ilde\AppData\Local\Programs\Python\Python310\python.exe -B G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\run_d08_checks.py open-finance`

Exit: 1; segundos: 1.0

```text
{"suite": "open-finance", "run": 90, "pass": 24, "fail": 66, "error": 0, "skip": 0, "individual": [["test_sqlite_validation.HttpTests.test_real_api_available_while_bank_waits_and_peer_finishes", "FAIL"], ["test_sqlite_validation.HttpTests.test_real_api_available_with_both_providers_unavailable", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_actual_workers_failure_isolated_and_all_threads_stop", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_auto_disabled_no_ingestion", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_binding_change_rejected_without_replacing_existing_connection", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_cancellation_inside_page_rolls_back_and_releases_lease", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_concurrent_manual_auto_same_bank_rejected_peer_continues", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_each_bank_auth_failure_leaves_peer_successful", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_existing_live_lease_not_stolen", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_malformed_page_rolls_back_both_staging_projections", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_missing_bank_credentials_do_not_prevent_valid_peer", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_partial_collection_fails_without_false_absence_or_peer_loss", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_repeated_automatic_ingestion_no_duplicates_or_promotion", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_restart_after_abrupt_interruption_of_uncommitted_page", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_restart_after_abrupt_interruption_with_committed_pages", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_same_external_ids_are_scoped_by_institution", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_schema10_migration_history_and_reapplication", "FAIL"], ["test_sqlite_validation.SQLiteTests.test_timeout_is_recorded_and_retry_is_idempotent", "FAIL"], ["test_cancellation.CancellationTests.test_cancellation_during_pagination_itau", "FAIL"], ["test_cancellation.CancellationTests.test_cancellation_during_pagination_santander", "FAIL"], ["test_cancellation.CancellationTests.test_cancellation_inside_persistence_rolls_back_entire_page", "FAIL"], ["test_cancellation.CancellationTests.test_cooperative_transport_cancellation", "FAIL"], ["test_cancellation.CancellationTests.test_deadline_bounds_wait_and_prevents_unbounded_retry_threads", "FAIL"], ["test_cancellation.CancellationTests.test_interrupt_cannot_be_recorded_without_reason", "FAIL"], ["test_cancellation.CancellationTests.test_itau_interrupted_santander_operational", "FAIL"], ["test_cancellation.CancellationTests.test_noncooperative_io_detached_not_reported_as_provider_cancelled", "FAIL"], ["test_cancellation.CancellationTests.test_old_worker_and_late_transport_cannot_write_over_new_owner", "FAIL"], ["test_cancellation.CancellationTests.test_santander_interrupted_itau_operational", "FAIL"], ["test_cancellation.CancellationTests.test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable", "FAIL"], ["test_cancellation.CancellationTests.test_timeout_error_releases_slot_and_peer_can_collect", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_binding_guard_precedes_schedule_optimization", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_expired_item_preserves_previously_ingested_products", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_failure_backoff_does_not_block_explicit_manual_collection", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_historical_invalid_and_valid_consents_select_current_authorization", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_interrupted_run_can_resume_without_cooldown", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_item_login_user_action_and_unknown_states_are_auditable", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_optional_consent_unavailable_does_not_invent_denial_for_other_products", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_restart_does_not_repeat_recent_automatic_success", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_revoked_consents_are_not_turned_into_empty_snapshots", "FAIL"], ["test_release_policy.ReleasePolicyTests.test_schedule_becomes_due_without_changing_product_timeout", "FAIL"], ["test_diagnostics.OriginTests.test_adversarial_metadata_is_strictly_reallowlisted_at_emit", "PASS"], ["test_diagnostics.OriginTests.test_auth_coverage_repeated_401_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_coverage_required_403_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_creation_refusal_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_legacy_repeated_401_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_legacy_required_403_origin", "PASS"], ["test_diagnostics.OriginTests.test_bool_status_and_foreign_context_types_cannot_leak", "PASS"], ["test_diagnostics.OriginTests.test_correlation_consistent_per_run_distinct_between_runs", "PASS"], ["test_diagnostics.OriginTests.test_non_target_error_not_annotated_or_logged", "PASS"], ["test_diagnostics.OriginTests.test_optional_403_behavior_and_no_diagnostic_preserved", "PASS"], ["test_diagnostics.OriginTests.test_path_classifier_never_returns_identifiers_or_query", "PASS"], ["test_diagnostics.OriginTests.test_scope_account_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_account_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_null_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_investment_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_foreign_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_missing_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_null_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_legacy_account_response", "PASS"], ["test_diagnostics.OriginTests.test_scope_legacy_transaction_membership", "PASS"], ["test_diagnostics.OriginTests.test_scope_loan_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_second_guard_optional_resource", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_auto_service_emits_once_and_keeps_existing_run_shape", "FAIL"], ["test_diagnostics.ServiceDiagnosticTests.test_concurrent_workers_emit_bank_local_context_and_stop", "FAIL"], ["test_diagnostics.ServiceDiagnosticTests.test_http_response_preserves_error_code_and_excludes_diagnostic", "FAIL"], ["test_diagnostics.ServiceDiagnosticTests.test_legacy_auth_failure_emits_once", "FAIL"], ["test_diagnostics.ServiceDiagnosticTests.test_logging_sink_failure_never_prevents_existing_finalization", "FAIL"], ["test_diagnostics.ServiceDiagnosticTests.test_sixth_scope_origin_real_persistence_guard_legacy", "FAIL"], ["stock_coverage.CoverageTests.test_absence_is_not_asserted_as_deletion", "FAIL"], ["stock_coverage.CoverageTests.test_all_products_projection_history_and_financial_preservation", "FAIL"], ["stock_coverage.CoverageTests.test_changed_balance_retains_original_history", "FAIL"], ["stock_coverage.CoverageTests.test_connection_disabled_binding_and_owner_guards", "FAIL"], ["stock_coverage.CoverageTests.test_contract_integrity_fails_closed", "FAIL"], ["stock_coverage.CoverageTests.test_corrupt_transaction_scope_fails_without_official_changes", "FAIL"], ["stock_coverage.CoverageTests.test_cursor_cycles_and_missing_next_rejected", "FAIL"], ["stock_coverage.CoverageTests.test_duplicate_and_foreign_item_rejected", "FAIL"], ["stock_coverage.CoverageTests.test_forbidden_live_endpoints_and_writes_fail_before_network", "FAIL"], ["stock_coverage.CoverageTests.test_http_auth_owner_and_validation", "FAIL"], ["stock_coverage.CoverageTests.test_http_manual_sync_and_resource_schema", "FAIL"], ["stock_coverage.CoverageTests.test_malformed_page_rolls_back_legacy_and_extended_rows_together", "FAIL"], ["stock_coverage.CoverageTests.test_no_implicit_auth_or_network_on_get", "FAIL"], ["stock_coverage.CoverageTests.test_paged_collection_complete_and_partial_page_rejected", "FAIL"], ["stock_coverage.CoverageTests.test_payment_and_loan_details_keep_financial_fields_not_identifiers", "FAIL"], ["stock_coverage.CoverageTests.test_query_pagination_and_integrity", "FAIL"], ["stock_coverage.CoverageTests.test_replay_does_not_duplicate_revisions", "FAIL"], ["stock_coverage.CoverageTests.test_schema8_to10_preservation_reapply_and_rollback", "FAIL"], ["stock_coverage.CoverageTests.test_unavailable_and_unauthorized_preserve_previous_values", "FAIL"], ["stock_coverage.CoverageTests.test_zero_null_absent_and_projection_types", "FAIL"]]}
test_real_api_available_while_bank_waits_and_peer_finishes (test_sqlite_validation.HttpTests) ... FAIL
test_real_api_available_with_both_providers_unavailable (test_sqlite_validation.HttpTests) ... FAIL
test_actual_workers_failure_isolated_and_all_threads_stop (test_sqlite_validation.SQLiteTests) ... FAIL
test_auto_disabled_no_ingestion (test_sqlite_validation.SQLiteTests) ... FAIL
test_binding_change_rejected_without_replacing_existing_connection (test_sqlite_validation.SQLiteTests) ... FAIL
test_cancellation_inside_page_rolls_back_and_releases_lease (test_sqlite_validation.SQLiteTests) ... FAIL
test_concurrent_manual_auto_same_bank_rejected_peer_continues (test_sqlite_validation.SQLiteTests) ... FAIL
test_each_bank_auth_failure_leaves_peer_successful (test_sqlite_validation.SQLiteTests) ... FAIL
test_existing_live_lease_not_stolen (test_sqlite_validation.SQLiteTests) ... FAIL
test_malformed_page_rolls_back_both_staging_projections (test_sqlite_validation.SQLiteTests) ... FAIL
test_missing_bank_credentials_do_not_prevent_valid_peer (test_sqlite_validation.SQLiteTests) ... FAIL
test_partial_collection_fails_without_false_absence_or_peer_loss (test_sqlite_validation.SQLiteTests) ... FAIL
test_repeated_automatic_ingestion_no_duplicates_or_promotion (test_sqlite_validation.SQLiteTests) ... FAIL
test_restart_after_abrupt_interruption_of_uncommitted_page (test_sqlite_validation.SQLiteTests) ... FAIL
test_restart_after_abrupt_interruption_with_committed_pages (test_sqlite_validation.SQLiteTests) ... FAIL
test_same_external_ids_are_scoped_by_institution (test_sqlite_validation.SQLiteTests) ... FAIL
test_schema10_migration_history_and_reapplication (test_sqlite_validation.SQLiteTests) ... FAIL
test_timeout_is_recorded_and_retry_is_idempotent (test_sqlite_validation.SQLiteTests) ... FAIL
test_cancellation_during_pagination_itau (test_cancellation.CancellationTests) ... FAIL
test_cancellation_during_pagination_santander (test_cancellation.CancellationTests) ... FAIL
test_cancellation_inside_persistence_rolls_back_entire_page (test_cancellation.CancellationTests) ... FAIL
test_cooperative_transport_cancellation (test_cancellation.CancellationTests) ... FAIL
test_deadline_bounds_wait_and_prevents_unbounded_retry_threads (test_cancellation.CancellationTests) ... FAIL
test_interrupt_cannot_be_recorded_without_reason (test_cancellation.CancellationTests) ... FAIL
test_itau_interrupted_santander_operational (test_cancellation.CancellationTests) ... FAIL
test_noncooperative_io_detached_not_reported_as_provider_cancelled (test_cancellation.CancellationTests) ... FAIL
test_old_worker_and_late_transport_cannot_write_over_new_owner (test_cancellation.CancellationTests) ... FAIL
test_santander_interrupted_itau_operational (test_cancellation.CancellationTests) ... FAIL
test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable (test_cancellation.CancellationTests) ... FAIL
test_timeout_error_releases_slot_and_peer_can_collect (test_cancellation.CancellationTests) ... FAIL
test_binding_guard_precedes_schedule_optimization (test_release_policy.ReleasePolicyTests) ... FAIL
test_expired_item_preserves_previously_ingested_products (test_release_policy.ReleasePolicyTests) ... FAIL
test_failure_backoff_does_not_block_explicit_manual_collection (test_release_policy.ReleasePolicyTests) ... FAIL
test_historical_invalid_and_valid_consents_select_current_authorization (test_release_policy.ReleasePolicyTests) ... FAIL
test_interrupted_run_can_resume_without_cooldown (test_release_policy.ReleasePolicyTests) ... FAIL
test_item_login_user_action_and_unknown_states_are_auditable (test_release_policy.ReleasePolicyTests) ... FAIL
test_optional_consent_unavailable_does_not_invent_denial_for_other_products (test_release_policy.ReleasePolicyTests) ... FAIL
test_restart_does_not_repeat_recent_automatic_success (test_release_policy.ReleasePolicyTests) ... FAIL
test_revoked_consents_are_not_turned_into_empty_snapshots (test_release_policy.ReleasePolicyTests) ... FAIL
test_schedule_becomes_due_without_changing_product_timeout (test_release_policy.ReleasePolicyTests) ... FAIL
test_adversarial_metadata_is_strictly_reallowlisted_at_emit (test_diagnostics.OriginTests) ... ok
test_auth_coverage_repeated_401_origin (test_diagnostics.OriginTests) ... ok
test_auth_coverage_required_403_origin (test_diagnostics.OriginTests) ... ok
test_auth_creation_refusal_origin (test_diagnostics.OriginTests) ... ok
test_auth_legacy_repeated_401_origin (test_diagnostics.OriginTests) ... ok
test_auth_legacy_required_403_origin (test_diagnostics.OriginTests) ... ok
test_bool_status_and_foreign_context_types_cannot_leak (test_diagnostics.OriginTests) ... ok
test_correlation_consistent_per_run_distinct_between_runs (test_diagnostics.OriginTests) ... ok
test_non_target_error_not_annotated_or_logged (test_diagnostics.OriginTests) ... ok
test_optional_403_behavior_and_no_diagnostic_preserved (test_diagnostics.OriginTests) ... ok
test_path_classifier_never_returns_identifiers_or_query (test_diagnostics.OriginTests) ... ok
test_scope_account_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_account_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_null_item (test_diagnostics.OriginTests) ... ok
test_scope_investment_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_item_foreign_id (test_diagnostics.OriginTests) ... ok
test_scope_item_missing_id (test_diagnostics.OriginTests) ... ok
test_scope_item_null_id (test_diagnostics.OriginTests) ... ok
test_scope_legacy_account_response (test_diagnostics.OriginTests) ... ok
test_scope_legacy_transaction_membership (test_diagnostics.OriginTests) ... ok
test_scope_loan_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_second_guard_optional_resource (test_diagnostics.OriginTests) ... ok
test_auto_service_emits_once_and_keeps_existing_run_shape (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_concurrent_workers_emit_bank_local_context_and_stop (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_http_response_preserves_error_code_and_excludes_diagnostic (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_legacy_auth_failure_emits_once (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_logging_sink_failure_never_prevents_existing_finalization (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_sixth_scope_origin_real_persistence_guard_legacy (test_diagnostics.ServiceDiagnosticTests) ... FAIL
test_absence_is_not_asserted_as_deletion (stock_coverage.CoverageTests) ... FAIL
test_all_products_projection_history_and_financial_preservation (stock_coverage.CoverageTests) ... FAIL
test_changed_balance_retains_original_history (stock_coverage.CoverageTests) ... FAIL
test_connection_disabled_binding_and_owner_guards (stock_coverage.CoverageTests) ... FAIL
test_contract_integrity_fails_closed (stock_coverage.CoverageTests) ... FAIL
test_corrupt_transaction_scope_fails_without_official_changes (stock_coverage.CoverageTests) ... FAIL
test_cursor_cycles_and_missing_next_rejected (stock_coverage.CoverageTests) ... FAIL
test_duplicate_and_foreign_item_rejected (stock_coverage.CoverageTests) ... FAIL
test_forbidden_live_endpoints_and_writes_fail_before_network (stock_coverage.CoverageTests) ... FAIL
test_http_auth_owner_and_validation (stock_coverage.CoverageTests) ... FAIL
test_http_manual_sync_and_resource_schema (stock_coverage.CoverageTests) ... FAIL
test_malformed_page_rolls_back_legacy_and_extended_rows_together (stock_coverage.CoverageTests) ... FAIL
test_no_implicit_auth_or_network_on_get (stock_coverage.CoverageTests) ... FAIL
test_paged_collection_complete_and_partial_page_rejected (stock_coverage.CoverageTests) ... FAIL
test_payment_and_loan_details_keep_financial_fields_not_identifiers (stock_coverage.CoverageTests) ... FAIL
test_query_pagination_and_integrity (stock_coverage.CoverageTests) ... FAIL
test_replay_does_not_duplicate_revisions (stock_coverage.CoverageTests) ... FAIL
test_schema8_to10_preservation_reapply_and_rollback (stock_coverage.CoverageTests) ... FAIL
test_unavailable_and_unauthorized_preserve_previous_values (stock_coverage.CoverageTests) ... FAIL
test_zero_null_absent_and_projection_types (stock_coverage.CoverageTests) ... FAIL

======================================================================
FAIL: test_real_api_available_while_bank_waits_and_peer_finishes (test_sqlite_validation.HttpTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_real_api_available_with_both_providers_unavailable (test_sqlite_validation.HttpTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_actual_workers_failure_isolated_and_all_threads_stop (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_auto_disabled_no_ingestion (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_binding_change_rejected_without_replacing_existing_connection (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cancellation_inside_page_rolls_back_and_releases_lease (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_concurrent_manual_auto_same_bank_rejected_peer_continues (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_each_bank_auth_failure_leaves_peer_successful (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_existing_live_lease_not_stolen (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_malformed_page_rolls_back_both_staging_projections (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_missing_bank_credentials_do_not_prevent_valid_peer (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_partial_collection_fails_without_false_absence_or_peer_loss (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_repeated_automatic_ingestion_no_duplicates_or_promotion (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_restart_after_abrupt_interruption_of_uncommitted_page (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_restart_after_abrupt_interruption_with_committed_pages (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_same_external_ids_are_scoped_by_institution (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_schema10_migration_history_and_reapplication (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_timeout_is_recorded_and_retry_is_idempotent (test_sqlite_validation.SQLiteTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cancellation_during_pagination_itau (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cancellation_during_pagination_santander (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cancellation_inside_persistence_rolls_back_entire_page (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cooperative_transport_cancellation (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_deadline_bounds_wait_and_prevents_unbounded_retry_threads (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_interrupt_cannot_be_recorded_without_reason (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_itau_interrupted_santander_operational (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_noncooperative_io_detached_not_reported_as_provider_cancelled (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_old_worker_and_late_transport_cannot_write_over_new_owner (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_santander_interrupted_itau_operational (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_timeout_error_releases_slot_and_peer_can_collect (test_cancellation.CancellationTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_binding_guard_precedes_schedule_optimization (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_expired_item_preserves_previously_ingested_products (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_failure_backoff_does_not_block_explicit_manual_collection (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_historical_invalid_and_valid_consents_select_current_authorization (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_interrupted_run_can_resume_without_cooldown (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_item_login_user_action_and_unknown_states_are_auditable (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_optional_consent_unavailable_does_not_invent_denial_for_other_products (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_restart_does_not_repeat_recent_automatic_success (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_revoked_consents_are_not_turned_into_empty_snapshots (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_schedule_becomes_due_without_changing_product_timeout (test_release_policy.ReleasePolicyTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_auto_service_emits_once_and_keeps_existing_run_shape (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_concurrent_workers_emit_bank_local_context_and_stop (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_http_response_preserves_error_code_and_excludes_diagnostic (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_legacy_auth_failure_emits_once (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_logging_sink_failure_never_prevents_existing_finalization (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_sixth_scope_origin_real_persistence_guard_legacy (test_diagnostics.ServiceDiagnosticTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\test_sqlite_validation.py", line 46, in setUp
    self.assertEqual(migrate(self.path), list(range(1,11)))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_absence_is_not_asserted_as_deletion (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_all_products_projection_history_and_financial_preservation (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_changed_balance_retains_original_history (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_connection_disabled_binding_and_owner_guards (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_contract_integrity_fails_closed (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_corrupt_transaction_scope_fails_without_official_changes (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_cursor_cycles_and_missing_next_rejected (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_duplicate_and_foreign_item_rejected (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_forbidden_live_endpoints_and_writes_fail_before_network (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_http_auth_owner_and_validation (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_http_manual_sync_and_resource_schema (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_malformed_page_rolls_back_legacy_and_extended_rows_together (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_no_implicit_auth_or_network_on_get (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_paged_collection_complete_and_partial_page_rejected (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_payment_and_loan_details_keep_financial_fields_not_identifiers (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_query_pagination_and_integrity (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_replay_does_not_duplicate_revisions (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_schema8_to10_preservation_reapply_and_rollback (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_unavailable_and_unauthorized_preserve_previous_values (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

======================================================================
FAIL: test_zero_null_absent_and_projection_types (stock_coverage.CoverageTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_full_coverage.py", line 91, in setUp
    migrations.migrate(self.db)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\migrations.py", line 62, in migrate
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\db.py", line 17, in connect
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\auto_sync\support.py", line 30, in audit
    raise AssertionError('DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES')
AssertionError: DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES

----------------------------------------------------------------------
Ran 90 tests in 0.127s

FAILED (failures=66)

```

## Correção do instrumental

A primeira rodada teve 24 PASS / 66 FAIL, sem ERROR/SKIP. O evento sqlite3.connect deste Python 3.10 Windows fornece caminho bytes; str(bytes) criava um caminho incorreto. Prova mínima independente confirmou args_type=bytes. support.audit agora usa os.fsdecode, sem alterar a guarda de raiz. Três controles adicionais verificam caminho bytes permitido e bytes/texto externos rejeitados, sem abrir banco externo. Nenhuma mudança de produto por esse erro.

## Open Finance consolidada após correção de fixture

Comando: `C:\Users\ilde\AppData\Local\Programs\Python\Python310\python.exe -B G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\run_d08_checks.py open-finance`

Exit: 0; segundos: 13.844

```text
{"suite": "open-finance", "run": 93, "pass": 93, "fail": 0, "error": 0, "skip": 0, "individual": [["__main__.FixtureBoundaryTests.test_native_bytes_inside_new_fixture_are_allowed", "PASS"], ["__main__.FixtureBoundaryTests.test_native_bytes_outside_fixture_remain_rejected", "PASS"], ["__main__.FixtureBoundaryTests.test_text_outside_fixture_remains_rejected", "PASS"], ["test_sqlite_validation.HttpTests.test_real_api_available_while_bank_waits_and_peer_finishes", "PASS"], ["test_sqlite_validation.HttpTests.test_real_api_available_with_both_providers_unavailable", "PASS"], ["test_sqlite_validation.SQLiteTests.test_actual_workers_failure_isolated_and_all_threads_stop", "PASS"], ["test_sqlite_validation.SQLiteTests.test_auto_disabled_no_ingestion", "PASS"], ["test_sqlite_validation.SQLiteTests.test_binding_change_rejected_without_replacing_existing_connection", "PASS"], ["test_sqlite_validation.SQLiteTests.test_cancellation_inside_page_rolls_back_and_releases_lease", "PASS"], ["test_sqlite_validation.SQLiteTests.test_concurrent_manual_auto_same_bank_rejected_peer_continues", "PASS"], ["test_sqlite_validation.SQLiteTests.test_each_bank_auth_failure_leaves_peer_successful", "PASS"], ["test_sqlite_validation.SQLiteTests.test_existing_live_lease_not_stolen", "PASS"], ["test_sqlite_validation.SQLiteTests.test_malformed_page_rolls_back_both_staging_projections", "PASS"], ["test_sqlite_validation.SQLiteTests.test_missing_bank_credentials_do_not_prevent_valid_peer", "PASS"], ["test_sqlite_validation.SQLiteTests.test_partial_collection_fails_without_false_absence_or_peer_loss", "PASS"], ["test_sqlite_validation.SQLiteTests.test_repeated_automatic_ingestion_no_duplicates_or_promotion", "PASS"], ["test_sqlite_validation.SQLiteTests.test_restart_after_abrupt_interruption_of_uncommitted_page", "PASS"], ["test_sqlite_validation.SQLiteTests.test_restart_after_abrupt_interruption_with_committed_pages", "PASS"], ["test_sqlite_validation.SQLiteTests.test_same_external_ids_are_scoped_by_institution", "PASS"], ["test_sqlite_validation.SQLiteTests.test_schema10_migration_history_and_reapplication", "PASS"], ["test_sqlite_validation.SQLiteTests.test_timeout_is_recorded_and_retry_is_idempotent", "PASS"], ["test_cancellation.CancellationTests.test_cancellation_during_pagination_itau", "PASS"], ["test_cancellation.CancellationTests.test_cancellation_during_pagination_santander", "PASS"], ["test_cancellation.CancellationTests.test_cancellation_inside_persistence_rolls_back_entire_page", "PASS"], ["test_cancellation.CancellationTests.test_cooperative_transport_cancellation", "PASS"], ["test_cancellation.CancellationTests.test_deadline_bounds_wait_and_prevents_unbounded_retry_threads", "PASS"], ["test_cancellation.CancellationTests.test_interrupt_cannot_be_recorded_without_reason", "PASS"], ["test_cancellation.CancellationTests.test_itau_interrupted_santander_operational", "PASS"], ["test_cancellation.CancellationTests.test_noncooperative_io_detached_not_reported_as_provider_cancelled", "PASS"], ["test_cancellation.CancellationTests.test_old_worker_and_late_transport_cannot_write_over_new_owner", "PASS"], ["test_cancellation.CancellationTests.test_santander_interrupted_itau_operational", "PASS"], ["test_cancellation.CancellationTests.test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable", "PASS"], ["test_cancellation.CancellationTests.test_timeout_error_releases_slot_and_peer_can_collect", "PASS"], ["test_release_policy.ReleasePolicyTests.test_binding_guard_precedes_schedule_optimization", "PASS"], ["test_release_policy.ReleasePolicyTests.test_expired_item_preserves_previously_ingested_products", "PASS"], ["test_release_policy.ReleasePolicyTests.test_failure_backoff_does_not_block_explicit_manual_collection", "PASS"], ["test_release_policy.ReleasePolicyTests.test_historical_invalid_and_valid_consents_select_current_authorization", "PASS"], ["test_release_policy.ReleasePolicyTests.test_interrupted_run_can_resume_without_cooldown", "PASS"], ["test_release_policy.ReleasePolicyTests.test_item_login_user_action_and_unknown_states_are_auditable", "PASS"], ["test_release_policy.ReleasePolicyTests.test_optional_consent_unavailable_does_not_invent_denial_for_other_products", "PASS"], ["test_release_policy.ReleasePolicyTests.test_restart_does_not_repeat_recent_automatic_success", "PASS"], ["test_release_policy.ReleasePolicyTests.test_revoked_consents_are_not_turned_into_empty_snapshots", "PASS"], ["test_release_policy.ReleasePolicyTests.test_schedule_becomes_due_without_changing_product_timeout", "PASS"], ["test_diagnostics.OriginTests.test_adversarial_metadata_is_strictly_reallowlisted_at_emit", "PASS"], ["test_diagnostics.OriginTests.test_auth_coverage_repeated_401_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_coverage_required_403_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_creation_refusal_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_legacy_repeated_401_origin", "PASS"], ["test_diagnostics.OriginTests.test_auth_legacy_required_403_origin", "PASS"], ["test_diagnostics.OriginTests.test_bool_status_and_foreign_context_types_cannot_leak", "PASS"], ["test_diagnostics.OriginTests.test_correlation_consistent_per_run_distinct_between_runs", "PASS"], ["test_diagnostics.OriginTests.test_non_target_error_not_annotated_or_logged", "PASS"], ["test_diagnostics.OriginTests.test_optional_403_behavior_and_no_diagnostic_preserved", "PASS"], ["test_diagnostics.OriginTests.test_path_classifier_never_returns_identifiers_or_query", "PASS"], ["test_diagnostics.OriginTests.test_scope_account_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_account_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_consent_null_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_investment_missing_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_foreign_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_missing_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_item_null_id", "PASS"], ["test_diagnostics.OriginTests.test_scope_legacy_account_response", "PASS"], ["test_diagnostics.OriginTests.test_scope_legacy_transaction_membership", "PASS"], ["test_diagnostics.OriginTests.test_scope_loan_foreign_item", "PASS"], ["test_diagnostics.OriginTests.test_scope_second_guard_optional_resource", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_auto_service_emits_once_and_keeps_existing_run_shape", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_concurrent_workers_emit_bank_local_context_and_stop", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_http_response_preserves_error_code_and_excludes_diagnostic", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_legacy_auth_failure_emits_once", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_logging_sink_failure_never_prevents_existing_finalization", "PASS"], ["test_diagnostics.ServiceDiagnosticTests.test_sixth_scope_origin_real_persistence_guard_legacy", "PASS"], ["stock_coverage.CoverageTests.test_absence_is_not_asserted_as_deletion", "PASS"], ["stock_coverage.CoverageTests.test_all_products_projection_history_and_financial_preservation", "PASS"], ["stock_coverage.CoverageTests.test_changed_balance_retains_original_history", "PASS"], ["stock_coverage.CoverageTests.test_connection_disabled_binding_and_owner_guards", "PASS"], ["stock_coverage.CoverageTests.test_contract_integrity_fails_closed", "PASS"], ["stock_coverage.CoverageTests.test_corrupt_transaction_scope_fails_without_official_changes", "PASS"], ["stock_coverage.CoverageTests.test_cursor_cycles_and_missing_next_rejected", "PASS"], ["stock_coverage.CoverageTests.test_duplicate_and_foreign_item_rejected", "PASS"], ["stock_coverage.CoverageTests.test_forbidden_live_endpoints_and_writes_fail_before_network", "PASS"], ["stock_coverage.CoverageTests.test_http_auth_owner_and_validation", "PASS"], ["stock_coverage.CoverageTests.test_http_manual_sync_and_resource_schema", "PASS"], ["stock_coverage.CoverageTests.test_malformed_page_rolls_back_legacy_and_extended_rows_together", "PASS"], ["stock_coverage.CoverageTests.test_no_implicit_auth_or_network_on_get", "PASS"], ["stock_coverage.CoverageTests.test_paged_collection_complete_and_partial_page_rejected", "PASS"], ["stock_coverage.CoverageTests.test_payment_and_loan_details_keep_financial_fields_not_identifiers", "PASS"], ["stock_coverage.CoverageTests.test_query_pagination_and_integrity", "PASS"], ["stock_coverage.CoverageTests.test_replay_does_not_duplicate_revisions", "PASS"], ["stock_coverage.CoverageTests.test_schema8_to10_preservation_reapply_and_rollback", "PASS"], ["stock_coverage.CoverageTests.test_unavailable_and_unauthorized_preserve_previous_values", "PASS"], ["stock_coverage.CoverageTests.test_zero_null_absent_and_projection_types", "PASS"]]}
test_native_bytes_inside_new_fixture_are_allowed (__main__.FixtureBoundaryTests) ... ok
test_native_bytes_outside_fixture_remain_rejected (__main__.FixtureBoundaryTests) ... ok
test_text_outside_fixture_remains_rejected (__main__.FixtureBoundaryTests) ... ok
test_real_api_available_while_bank_waits_and_peer_finishes (test_sqlite_validation.HttpTests) ... ok
test_real_api_available_with_both_providers_unavailable (test_sqlite_validation.HttpTests) ... ok
test_actual_workers_failure_isolated_and_all_threads_stop (test_sqlite_validation.SQLiteTests) ... ok
test_auto_disabled_no_ingestion (test_sqlite_validation.SQLiteTests) ... ok
test_binding_change_rejected_without_replacing_existing_connection (test_sqlite_validation.SQLiteTests) ... ok
test_cancellation_inside_page_rolls_back_and_releases_lease (test_sqlite_validation.SQLiteTests) ... ok
test_concurrent_manual_auto_same_bank_rejected_peer_continues (test_sqlite_validation.SQLiteTests) ... ok
test_each_bank_auth_failure_leaves_peer_successful (test_sqlite_validation.SQLiteTests) ... OPEN_FINANCE_DIAGNOSTIC {"category":"AUTH_REQUEST_REJECTED","correlation_id":"ofdiag-facfe7476d76e971269f7d3c","error_code":"AUTH_FAILED","event":"OPEN_FINANCE_DIAGNOSTIC","http_status":401,"institution":"ITAU","operation":"AUTH_CREATE","resource":"other","stage":"TOKEN_ACQUISITION","version":"D02/1"}
OPEN_FINANCE_DIAGNOSTIC {"category":"AUTH_REQUEST_REJECTED","correlation_id":"ofdiag-48748cb01cb1f5735f0cc098","error_code":"AUTH_FAILED","event":"OPEN_FINANCE_DIAGNOSTIC","http_status":401,"institution":"SANTANDER","operation":"AUTH_CREATE","resource":"other","stage":"TOKEN_ACQUISITION","version":"D02/1"}
ok
test_existing_live_lease_not_stolen (test_sqlite_validation.SQLiteTests) ... ok
test_malformed_page_rolls_back_both_staging_projections (test_sqlite_validation.SQLiteTests) ... ok
test_missing_bank_credentials_do_not_prevent_valid_peer (test_sqlite_validation.SQLiteTests) ... OPEN_FINANCE_CONNECTION_INVALID_ITAU
ok
test_partial_collection_fails_without_false_absence_or_peer_loss (test_sqlite_validation.SQLiteTests) ... ok
test_repeated_automatic_ingestion_no_duplicates_or_promotion (test_sqlite_validation.SQLiteTests) ... ok
test_restart_after_abrupt_interruption_of_uncommitted_page (test_sqlite_validation.SQLiteTests) ... ok
test_restart_after_abrupt_interruption_with_committed_pages (test_sqlite_validation.SQLiteTests) ... ok
test_same_external_ids_are_scoped_by_institution (test_sqlite_validation.SQLiteTests) ... ok
test_schema10_migration_history_and_reapplication (test_sqlite_validation.SQLiteTests) ... ok
test_timeout_is_recorded_and_retry_is_idempotent (test_sqlite_validation.SQLiteTests) ... ok
test_cancellation_during_pagination_itau (test_cancellation.CancellationTests) ... coverage IO_DETACHED count=1
ok
test_cancellation_during_pagination_santander (test_cancellation.CancellationTests) ... coverage IO_DETACHED count=1
ok
test_cancellation_inside_persistence_rolls_back_entire_page (test_cancellation.CancellationTests) ... ok
test_cooperative_transport_cancellation (test_cancellation.CancellationTests) ... ok
test_deadline_bounds_wait_and_prevents_unbounded_retry_threads (test_cancellation.CancellationTests) ... ok
test_interrupt_cannot_be_recorded_without_reason (test_cancellation.CancellationTests) ... ok
test_itau_interrupted_santander_operational (test_cancellation.CancellationTests) ... coverage IO_DETACHED count=1
ok
test_noncooperative_io_detached_not_reported_as_provider_cancelled (test_cancellation.CancellationTests) ... ok
test_old_worker_and_late_transport_cannot_write_over_new_owner (test_cancellation.CancellationTests) ... coverage IO_DETACHED count=1
ok
test_santander_interrupted_itau_operational (test_cancellation.CancellationTests) ... coverage IO_DETACHED count=1
ok
test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable (test_cancellation.CancellationTests) ... ok
test_timeout_error_releases_slot_and_peer_can_collect (test_cancellation.CancellationTests) ... ok
test_binding_guard_precedes_schedule_optimization (test_release_policy.ReleasePolicyTests) ... ok
test_expired_item_preserves_previously_ingested_products (test_release_policy.ReleasePolicyTests) ... ok
test_failure_backoff_does_not_block_explicit_manual_collection (test_release_policy.ReleasePolicyTests) ... ok
test_historical_invalid_and_valid_consents_select_current_authorization (test_release_policy.ReleasePolicyTests) ... ok
test_interrupted_run_can_resume_without_cooldown (test_release_policy.ReleasePolicyTests) ... ok
test_item_login_user_action_and_unknown_states_are_auditable (test_release_policy.ReleasePolicyTests) ... ok
test_optional_consent_unavailable_does_not_invent_denial_for_other_products (test_release_policy.ReleasePolicyTests) ... ok
test_restart_does_not_repeat_recent_automatic_success (test_release_policy.ReleasePolicyTests) ... ok
test_revoked_consents_are_not_turned_into_empty_snapshots (test_release_policy.ReleasePolicyTests) ... ok
test_schedule_becomes_due_without_changing_product_timeout (test_release_policy.ReleasePolicyTests) ... ok
test_adversarial_metadata_is_strictly_reallowlisted_at_emit (test_diagnostics.OriginTests) ... ok
test_auth_coverage_repeated_401_origin (test_diagnostics.OriginTests) ... ok
test_auth_coverage_required_403_origin (test_diagnostics.OriginTests) ... ok
test_auth_creation_refusal_origin (test_diagnostics.OriginTests) ... ok
test_auth_legacy_repeated_401_origin (test_diagnostics.OriginTests) ... ok
test_auth_legacy_required_403_origin (test_diagnostics.OriginTests) ... ok
test_bool_status_and_foreign_context_types_cannot_leak (test_diagnostics.OriginTests) ... ok
test_correlation_consistent_per_run_distinct_between_runs (test_diagnostics.OriginTests) ... ok
test_non_target_error_not_annotated_or_logged (test_diagnostics.OriginTests) ... ok
test_optional_403_behavior_and_no_diagnostic_preserved (test_diagnostics.OriginTests) ... ok
test_path_classifier_never_returns_identifiers_or_query (test_diagnostics.OriginTests) ... ok
test_scope_account_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_account_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_consent_null_item (test_diagnostics.OriginTests) ... ok
test_scope_investment_missing_item (test_diagnostics.OriginTests) ... ok
test_scope_item_foreign_id (test_diagnostics.OriginTests) ... ok
test_scope_item_missing_id (test_diagnostics.OriginTests) ... ok
test_scope_item_null_id (test_diagnostics.OriginTests) ... ok
test_scope_legacy_account_response (test_diagnostics.OriginTests) ... ok
test_scope_legacy_transaction_membership (test_diagnostics.OriginTests) ... ok
test_scope_loan_foreign_item (test_diagnostics.OriginTests) ... ok
test_scope_second_guard_optional_resource (test_diagnostics.OriginTests) ... ok
test_auto_service_emits_once_and_keeps_existing_run_shape (test_diagnostics.ServiceDiagnosticTests) ... ok
test_concurrent_workers_emit_bank_local_context_and_stop (test_diagnostics.ServiceDiagnosticTests) ... ok
test_http_response_preserves_error_code_and_excludes_diagnostic (test_diagnostics.ServiceDiagnosticTests) ... ok
test_legacy_auth_failure_emits_once (test_diagnostics.ServiceDiagnosticTests) ... ok
test_logging_sink_failure_never_prevents_existing_finalization (test_diagnostics.ServiceDiagnosticTests) ... ok
test_sixth_scope_origin_real_persistence_guard_legacy (test_diagnostics.ServiceDiagnosticTests) ... ok
test_absence_is_not_asserted_as_deletion (stock_coverage.CoverageTests) ... ok
test_all_products_projection_history_and_financial_preservation (stock_coverage.CoverageTests) ... ok
test_changed_balance_retains_original_history (stock_coverage.CoverageTests) ... ok
test_connection_disabled_binding_and_owner_guards (stock_coverage.CoverageTests) ... ok
test_contract_integrity_fails_closed (stock_coverage.CoverageTests) ... ok
test_corrupt_transaction_scope_fails_without_official_changes (stock_coverage.CoverageTests) ... ok
test_cursor_cycles_and_missing_next_rejected (stock_coverage.CoverageTests) ... ok
test_duplicate_and_foreign_item_rejected (stock_coverage.CoverageTests) ... OPEN_FINANCE_DIAGNOSTIC {"category":"ITEM_ID_DIFFERENT","correlation_id":"ofdiag-ff20135ffebe8887a875b3c9","error_code":"ACCOUNT_SCOPE_MISMATCH","event":"OPEN_FINANCE_DIAGNOSTIC","http_status":null,"institution":"OTHER","operation":"LOANS_LIST","resource":"loans","stage":"SCOPE_CHECK","version":"D02/1"}
ok
test_forbidden_live_endpoints_and_writes_fail_before_network (stock_coverage.CoverageTests) ... ok
test_http_auth_owner_and_validation (stock_coverage.CoverageTests) ... ok
test_http_manual_sync_and_resource_schema (stock_coverage.CoverageTests) ... ok
test_malformed_page_rolls_back_legacy_and_extended_rows_together (stock_coverage.CoverageTests) ... ok
test_no_implicit_auth_or_network_on_get (stock_coverage.CoverageTests) ... ok
test_paged_collection_complete_and_partial_page_rejected (stock_coverage.CoverageTests) ... ok
test_payment_and_loan_details_keep_financial_fields_not_identifiers (stock_coverage.CoverageTests) ... ok
test_query_pagination_and_integrity (stock_coverage.CoverageTests) ... ok
test_replay_does_not_duplicate_revisions (stock_coverage.CoverageTests) ... ok
test_schema8_to10_preservation_reapply_and_rollback (stock_coverage.CoverageTests) ... ok
test_unavailable_and_unauthorized_preserve_previous_values (stock_coverage.CoverageTests) ... ok
test_zero_null_absent_and_projection_types (stock_coverage.CoverageTests) ... ok

----------------------------------------------------------------------
Ran 93 tests in 13.255s

OK

```

## Domínio financeiro

Comando: `C:\Users\ilde\AppData\Local\Programs\Python\Python310\python.exe -B G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\run_d08_checks.py financial G:\Codex\Finance_V2\tests`

Exit: 0; segundos: 7.531

```text
{"suite": "financial", "run": 48, "pass": 48, "fail": 0, "error": 0, "skip": 0, "individual": [["__main__.FixtureBoundaryTests.test_native_bytes_inside_new_fixture_are_allowed", "PASS"], ["__main__.FixtureBoundaryTests.test_native_bytes_outside_fixture_remain_rejected", "PASS"], ["__main__.FixtureBoundaryTests.test_text_outside_fixture_remains_rejected", "PASS"], ["tests.test_domain.ConcurrencyTests.test_concurrent_materialization_creates_each_slot_once", "PASS"], ["tests.test_domain.ConcurrencyTests.test_concurrent_pay_pay_has_one_effect", "PASS"], ["tests.test_domain.DomainTests.test_automation_primitives_enforce_identity_retry_and_precedence_shapes", "PASS"], ["tests.test_domain.DomainTests.test_calendar_clamp_due_rule_and_lineage", "PASS"], ["tests.test_domain.DomainTests.test_cycle_boundary_invoice_snapshot_close_pay_reverse_revision", "PASS"], ["tests.test_domain.DomainTests.test_expense_status_lifecycle_and_audit_history", "PASS"], ["tests.test_domain.DomainTests.test_inactive_dependencies_are_rejected_without_rewriting_history", "PASS"], ["tests.test_domain.DomainTests.test_installments_exact_sum_and_terminal_cancel_remaining", "PASS"], ["tests.test_domain.DomainTests.test_invoice_financial_commands_are_idempotent", "PASS"], ["tests.test_domain.DomainTests.test_money_distribution_and_validation", "PASS"], ["tests.test_domain.DomainTests.test_occurrence_override_is_single_source_and_audited", "PASS"], ["tests.test_domain.DomainTests.test_payment_is_integral_idempotent_and_blocks_edit_cancel", "PASS"], ["tests.test_domain.DomainTests.test_recurrence_materialization_all_frequencies_idempotent_and_terminal", "PASS"], ["tests.test_domain.DomainTests.test_reversal_and_replacement_preserve_history", "PASS"], ["tests.test_revenues_v17.RevenueDomainTests.test_all_recurrence_frequencies_and_calendar_clamping", "PASS"], ["tests.test_revenues_v17.RevenueDomainTests.test_each_financial_command_replays_and_rejects_payload_conflict", "PASS"], ["tests.test_revenues_v17.RevenueDomainTests.test_lifecycle_status_tags_audit_and_reports", "PASS"], ["tests.test_revenues_v17.RevenueDomainTests.test_permanent_replay_survives_cache_removal_and_failed_effect_rolls_back", "PASS"], ["tests.test_revenues_v17.RevenueDomainTests.test_recurrence_calendar_tags_replay_and_scheduler", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_concurrent_equivalent_and_conflicting_requests_have_one_effect", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_concurrent_receipt_requests_leave_exactly_one_active_receipt", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_http_crud_replay_conflict_filters_openapi_and_persisted_effect", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_http_filters_pagination_aggregates_edit_cancel_reverse_and_audit", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_recurring_http_create_materialize_replay_detail_and_end", "PASS"], ["tests.test_revenues_v17.RevenueHttpTests.test_ui_bundle_exposes_complete_revenue_flows_without_cent_input", "PASS"], ["tests.test_scheduler.SchedulerConcurrencyTests.test_T168_two_schedulers_create_one_payment", "PASS"], ["tests.test_scheduler.SchedulerConcurrencyTests.test_T169_T170_T171_T590_concurrent_manual_config_cancel_are_serializable", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N04_F4N05_paid_on_is_real_execution_date_after_downtime", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N07_new_settlement_successor_has_independent_attempt_group", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N10_F4N16_empty_tick_is_observable_and_clean", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N10_scheduler_loop_waits_configured_interval_before_next_tick", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N11_batch_boundary_is_stable_across_ticks", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N13_manual_partial_reduces_invoice_auto_amount", "PASS"], ["tests.test_scheduler.SchedulerTests.test_F4N17_scheduler_uses_only_v2_database_configuration", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T092_F4N01_F4N02_F4N03_startup_catchup_and_year_horizon", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T157_T159_T160_T161_F4N15_expense_success_identity_actor_and_replay", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T158_T151_invoice_success_uses_permanent_identity", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T162_T166_F4N06_F4N09_retry_survives_restart_and_third_is_attention", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T163_T165_F4N14_inactive_account_attention", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T164_T172_T514_manual_wins_then_scheduler_skips", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T167_F4N08_failure_isolated_from_next_obligation", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T170_T171_selected_candidate_revalidates_account_and_cancellation", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T173_get_contract_is_covered_without_scheduler_side_effect_hook", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T391_scheduler_after_reverse_records_one_skipped_and_never_repays", "PASS"], ["tests.test_scheduler.SchedulerTests.test_T588_F4N12_open_overdue_invoice_closes_or_cancels_atomically", "PASS"]]}
test_native_bytes_inside_new_fixture_are_allowed (__main__.FixtureBoundaryTests) ... ok
test_native_bytes_outside_fixture_remain_rejected (__main__.FixtureBoundaryTests) ... ok
test_text_outside_fixture_remains_rejected (__main__.FixtureBoundaryTests) ... ok
test_concurrent_materialization_creates_each_slot_once (tests.test_domain.ConcurrencyTests) ... ok
test_concurrent_pay_pay_has_one_effect (tests.test_domain.ConcurrencyTests) ... ok
test_automation_primitives_enforce_identity_retry_and_precedence_shapes (tests.test_domain.DomainTests) ... ok
test_calendar_clamp_due_rule_and_lineage (tests.test_domain.DomainTests) ... ok
test_cycle_boundary_invoice_snapshot_close_pay_reverse_revision (tests.test_domain.DomainTests) ... ok
test_expense_status_lifecycle_and_audit_history (tests.test_domain.DomainTests) ... ok
test_inactive_dependencies_are_rejected_without_rewriting_history (tests.test_domain.DomainTests) ... ok
test_installments_exact_sum_and_terminal_cancel_remaining (tests.test_domain.DomainTests) ... ok
test_invoice_financial_commands_are_idempotent (tests.test_domain.DomainTests) ... ok
test_money_distribution_and_validation (tests.test_domain.DomainTests) ... ok
test_occurrence_override_is_single_source_and_audited (tests.test_domain.DomainTests) ... ok
test_payment_is_integral_idempotent_and_blocks_edit_cancel (tests.test_domain.DomainTests) ... ok
test_recurrence_materialization_all_frequencies_idempotent_and_terminal (tests.test_domain.DomainTests) ... ok
test_reversal_and_replacement_preserve_history (tests.test_domain.DomainTests) ... ok
test_all_recurrence_frequencies_and_calendar_clamping (tests.test_revenues_v17.RevenueDomainTests) ... ok
test_each_financial_command_replays_and_rejects_payload_conflict (tests.test_revenues_v17.RevenueDomainTests) ... ok
test_lifecycle_status_tags_audit_and_reports (tests.test_revenues_v17.RevenueDomainTests) ... ok
test_permanent_replay_survives_cache_removal_and_failed_effect_rolls_back (tests.test_revenues_v17.RevenueDomainTests) ... ok
test_recurrence_calendar_tags_replay_and_scheduler (tests.test_revenues_v17.RevenueDomainTests) ... ok
test_concurrent_equivalent_and_conflicting_requests_have_one_effect (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_concurrent_receipt_requests_leave_exactly_one_active_receipt (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_http_crud_replay_conflict_filters_openapi_and_persisted_effect (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_http_filters_pagination_aggregates_edit_cancel_reverse_and_audit (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_recurring_http_create_materialize_replay_detail_and_end (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_ui_bundle_exposes_complete_revenue_flows_without_cent_input (tests.test_revenues_v17.RevenueHttpTests) ... ok
test_T168_two_schedulers_create_one_payment (tests.test_scheduler.SchedulerConcurrencyTests) ... ok
test_T169_T170_T171_T590_concurrent_manual_config_cancel_are_serializable (tests.test_scheduler.SchedulerConcurrencyTests) ... ok
test_F4N04_F4N05_paid_on_is_real_execution_date_after_downtime (tests.test_scheduler.SchedulerTests) ... ok
test_F4N07_new_settlement_successor_has_independent_attempt_group (tests.test_scheduler.SchedulerTests) ... ok
test_F4N10_F4N16_empty_tick_is_observable_and_clean (tests.test_scheduler.SchedulerTests) ... ok
test_F4N10_scheduler_loop_waits_configured_interval_before_next_tick (tests.test_scheduler.SchedulerTests) ... ok
test_F4N11_batch_boundary_is_stable_across_ticks (tests.test_scheduler.SchedulerTests) ... ok
test_F4N13_manual_partial_reduces_invoice_auto_amount (tests.test_scheduler.SchedulerTests) ... ok
test_F4N17_scheduler_uses_only_v2_database_configuration (tests.test_scheduler.SchedulerTests) ... ok
test_T092_F4N01_F4N02_F4N03_startup_catchup_and_year_horizon (tests.test_scheduler.SchedulerTests) ... ok
test_T157_T159_T160_T161_F4N15_expense_success_identity_actor_and_replay (tests.test_scheduler.SchedulerTests) ... ok
test_T158_T151_invoice_success_uses_permanent_identity (tests.test_scheduler.SchedulerTests) ... ok
test_T162_T166_F4N06_F4N09_retry_survives_restart_and_third_is_attention (tests.test_scheduler.SchedulerTests) ... ok
test_T163_T165_F4N14_inactive_account_attention (tests.test_scheduler.SchedulerTests) ... ok
test_T164_T172_T514_manual_wins_then_scheduler_skips (tests.test_scheduler.SchedulerTests) ... ok
test_T167_F4N08_failure_isolated_from_next_obligation (tests.test_scheduler.SchedulerTests) ... scheduler candidate failed obligation_type=EXPENSE obligation_id=1
Traceback (most recent call last):
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\scheduler\service.py", line 173, in run_tick
    summary.result(self._execute(candidate))
  File "G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17\src\finance_v2\scheduler\service.py", line 129, in _execute
    return executor(connection, **({"expense_id": obligation_id} if kind == "EXPENSE" else {"invoice_id": obligation_id}), attempt_group_key=group, attempt_number=number, clock=self.clock)
  File "G:\Codex\Finance_V2\tests\test_scheduler.py", line 59, in selective
    if kwargs["expense_id"]==first:raise RuntimeError("unexpected")
RuntimeError: unexpected
ok
test_T170_T171_selected_candidate_revalidates_account_and_cancellation (tests.test_scheduler.SchedulerTests) ... ok
test_T173_get_contract_is_covered_without_scheduler_side_effect_hook (tests.test_scheduler.SchedulerTests) ... ok
test_T391_scheduler_after_reverse_records_one_skipped_and_never_repays (tests.test_scheduler.SchedulerTests) ... ok
test_T588_F4N12_open_overdue_invoice_closes_or_cancels_atomically (tests.test_scheduler.SchedulerTests) ... ok

----------------------------------------------------------------------
Ran 48 tests in 6.959s

OK

```

## MCP release

Comando: `C:\Users\ilde\AppData\Local\Programs\Python\Python310\python.exe -B G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\release_mcp.py`

Exit: 0; segundos: 0.516

```text
test_initialize_exact_release_and_protocol (__main__.ReleaseMcpTests) ... ok
test_missing_token_stays_unauthenticated (__main__.ReleaseMcpTests) ... ok
test_owner_cannot_use_external_mcp (__main__.ReleaseMcpTests) ... ok
test_sse_transport_preserves_initialize (__main__.ReleaseMcpTests) ... ok
test_tools_contract_unchanged (__main__.ReleaseMcpTests) ... ok
test_unknown_method_still_rejected (__main__.ReleaseMcpTests) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.067s

OK

```

## Build ARM64

`docker build --platform linux/arm64 --pull=false --network none --progress plain -t finance-v17-d08:0.1.26-open-finance.1-arm64 G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17`

Exit: 1; segundos: 23.7

```text
#0 building with "desktop-linux" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 924B 0.0s done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#2 DONE 0.0s

#3 [internal] load .dockerignore
#3 transferring context: 90B done
#3 DONE 0.0s

#4 [1/9] FROM docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#4 DONE 0.0s

#5 [internal] load build context
#5 transferring context: 900.36kB 0.1s done
#5 DONE 0.1s

#6 [2/9] WORKDIR /opt/finance-v2
#6 CACHED

#7 [3/9] COPY requirements-deploy.txt ./
#7 CACHED

#8 [4/9] RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2
#8 13.85 WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94ae6c2a80>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
#8 14.36 WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94afd02480>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
#8 16.52 WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69700>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
#8 18.53 WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69bb0>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
#8 22.53 WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69df0>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
#8 22.58 ERROR: Could not find a version that satisfies the requirement gunicorn==23.0.0 (from versions: none)
#8 22.59 ERROR: No matching distribution found for gunicorn==23.0.0
#8 ERROR: process "/bin/sh -c pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2" did not complete successfully: exit code: 1
------
 > [4/9] RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2:
13.85 WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94ae6c2a80>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
14.36 WARNING: Retrying (Retry(total=3, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94afd02480>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
16.52 WARNING: Retrying (Retry(total=2, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69700>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
18.53 WARNING: Retrying (Retry(total=1, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69bb0>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
22.53 WARNING: Retrying (Retry(total=0, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError('<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7c94adb69df0>: Failed to establish a new connection: [Errno -3] Temporary failure in name resolution')': /simple/gunicorn/
22.58 ERROR: Could not find a version that satisfies the requirement gunicorn==23.0.0 (from versions: none)
22.59 ERROR: No matching distribution found for gunicorn==23.0.0
------
Dockerfile:8
--------------------
   7 |     COPY requirements-deploy.txt ./
   8 | >>> RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt \
   9 | >>>     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2
  10 |     COPY --chown=financev2:financev2 src ./src
--------------------
ERROR: failed to build: failed to solve: process "/bin/sh -c pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2" did not complete successfully: exit code: 1

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/mi7mixivfkq5iwsh6abxg9vnv

```

## Build ARM64 com dependências públicas fixadas

A tentativa anterior offline não tinha cache da camada pip; nenhum produto foi alterado para contornar a falha.

`docker build --platform linux/arm64 --pull=false --network default --progress plain -t finance-v17-d08:0.1.26-open-finance.1-arm64 G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\finance-v17`

Exit: 0; segundos: 1.19

```text
#0 building with "desktop-linux" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 924B done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#2 DONE 0.0s

#3 [internal] load .dockerignore
#3 transferring context: 90B done
#3 DONE 0.0s

#4 [1/9] FROM docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#4 DONE 0.0s

#5 [internal] load build context
#5 transferring context: 4.47kB done
#5 DONE 0.0s

#6 [3/9] COPY requirements-deploy.txt ./
#6 CACHED

#7 [2/9] WORKDIR /opt/finance-v2
#7 CACHED

#8 [4/9] RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2
#8 CACHED

#9 [5/9] COPY --chown=financev2:financev2 src ./src
#9 DONE 0.1s

#10 [6/9] COPY --chown=financev2:financev2 migrations ./migrations
#10 DONE 0.0s

#11 [7/9] COPY --chown=financev2:financev2 run.sh ./run.sh
#11 DONE 0.0s

#12 [8/9] COPY --chown=financev2:financev2 migrate.sh ./migrate.sh
#12 DONE 0.0s

#13 [9/9] RUN chmod 0755 /opt/finance-v2/run.sh /opt/finance-v2/migrate.sh
#13 DONE 0.4s

#14 exporting to image
#14 exporting layers 0.1s done
#14 writing image sha256:ffee0d83f364bc4d163ac5c303a20512f812bf3030b4024cefa99f4f3cefbc09 done
#14 naming to docker.io/library/finance-v17-d08:0.1.26-open-finance.1-arm64 done
#14 DONE 0.1s

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/wjo9a12aec9qtdjf28rifiarx

```

```json
{
  "Id": "sha256:ffee0d83f364bc4d163ac5c303a20512f812bf3030b4024cefa99f4f3cefbc09",
  "Architecture": "arm64",
  "Os": "linux",
  "version": "0.1.26-open-finance.1"
}
```

## Resposta assíncrona tardia antes da correção

```text
✔ coverage HTTP 502 preserves only a known run error without raw response (1.3846ms)
✔ messages distinguish auth scope consent network internal without guessing invalid credentials (0.3044ms)
✔ unrelated API errors and success retain the existing contract (0.3081ms)
✔ network failure does not repeat a non-idempotent coverage request (0.2139ms)
✔ manual coverage handler renders the classified failure and always releases controls (0.7021ms)
✔ history uses the same closed vocabulary; no sync is added to initial render (0.2638ms)
✖ a late progress response cannot overwrite the final classified failure (1.4733ms)
ℹ tests 7
ℹ suites 0
ℹ pass 6
ℹ fail 1
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 93.8289

✖ failing tests:

test at ..\FinanceOpenFinanceD08-20261026-01\candidate\tests\test_d08_ui.mjs:68:1
✖ a late progress response cannot overwrite the final classified failure (1.4733ms)
  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected

  + '1 coleções em andamento; consulte os estados por recurso.'
  - 'Autenticação recusada pela Pluggy; o motivo não foi confirmado. Verifique o diagnóstico sanitizado antes de alterar credenciais.'

      at TestContext.<anonymous> (file:///G:/Codex/FinanceOpenFinanceD08-20261026-01/candidate/tests/test_d08_ui.mjs:81:10)
      at async Test.run (node:internal/test_runner/test:1389:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:960:7) {
    generatedMessage: true,
    code: 'ERR_ASSERTION',
    actual: '1 coleções em andamento; consulte os estados por recurso.',
    expected: 'Autenticação recusada pela Pluggy; o motivo não foi confirmado. Verifique o diagnóstico sanitizado antes de alterar credenciais.',
    operator: 'strictEqual',
    diff: 'simple'
  }

```

## Imagem ARM64: bytes, autenticação e wrapper real

`C:\Users\ilde\AppData\Local\Programs\Python\Python310\python.exe -B G:\Codex\FinanceOpenFinanceD08-20261026-01\candidate\tests\run_d08_image_checks.py sha256:ffee0d83f364bc4d163ac5c303a20512f812bf3030b4024cefa99f4f3cefbc09`

Exit 0

```text
{"image_files_verified": 80, "architecture": "aarch64"}

{"case": "ARM64_wrapper_TERM", "exit_code": 0, "ready_seconds": 33.922, "shutdown_seconds": 2.36, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}
{"case": "ARM64_wrapper_INT", "exit_code": 0, "ready_seconds": 31.859, "shutdown_seconds": 1.625, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}
{"owned_containers_removed": 4, "host_mounts": 0, "real_requests": 0}
{"result": "PASS", "cases": [{"case": "ARM64_auth", "pass": 8}, {"case": "ARM64_wrapper_TERM", "exit_code": 0, "ready_seconds": 33.922, "shutdown_seconds": 2.36, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}, {"case": "ARM64_wrapper_INT", "exit_code": 0, "ready_seconds": 31.859, "shutdown_seconds": 1.625, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}]}

```

## Validação de escopo e integridade

```text
{
  "result": "PASS",
  "negative_controls": 3,
  "version": "0.1.26-open-finance.1",
  "schema": 10,
  "product_files": 85,
  "protected_files": 8,
  "changed_product_files": [
    "finance-v17/CHANGELOG.md",
    "finance-v17/DOCS.md",
    "finance-v17/Dockerfile",
    "finance-v17/config.yaml",
    "finance-v17/src/finance_v2/__init__.py",
    "finance-v17/src/finance_v2/pluggy_client.py",
    "finance-v17/src/finance_v2/web/app.js",
    "finance-v17/src/finance_v2/web/open-finance-coverage.js",
    "finance-v17/src/finance_v2/web/open-finance-errors.js",
    "finance-v17/src/finance_v2/web/open-finance.js"
  ],
  "sha256": {
    "finance-v17/.dockerignore": "E9904728DA8956404E355E80B261B2B5BC2B584737907D94A3DEA72E595ECBD0",
    "finance-v17/CHANGELOG.md": "104050EA4BD7E2564A2A12E7DD2A326DBD8C2E275F5C8F13B3A9AAA29BE8A477",
    "finance-v17/DOCS.md": "14A8E4BCEDDD86D25BDA846B887916F1BABCFBB2580205D162B821C1228D135F",
    "finance-v17/Dockerfile": "9A143D10F0C1B4E4FD257B14CE06169D1387D45B7B1873D14EC53DE955D8B46D",
    "finance-v17/config.yaml": "DEDBE1B586C048C8DF7FB60E73A99ECC1124CBA6E403C5A7933B6347B44126D0",
    "finance-v17/migrate.sh": "488C3E2915F3AA3E07D3622B1BC5C996296B1BF2ECC265DEF868107879BE90C6",
    "finance-v17/migrations/001_v16_schema.sql": "4D007847DE4A76B0D190DE065782831E94A1DE698FEEDB8BE0CB14E42DF014B7",
    "finance-v17/migrations/002_v17_revenues.sql": "E4C8972DBFE6271F0AD02897FFDDF5B1A3544EE5074B7315F390F1E9BD2B70C0",
    "finance-v17/migrations/003_v17_recurring_revenues.sql": "F5F6D6AABF85F66B1AF2E44436E193404EC2FE6B6078EDB559272AC6166C6FD6",
    "finance-v17/migrations/004_v17_multimethod_installments.sql": "500B389C804C259E5953B7E4719E07FF543E65D0EDF5D4C8CCB0B908F92620C8",
    "finance-v17/migrations/005_v17_expense_tombstone.sql": "7D29C5151AD4703001F2C1F76482A48650EFD2D92E8976D7B93C3C54282B2F86",
    "finance-v17/migrations/006_v17_revenue_recurrence_versions.sql": "E7DAA63B8B8174D416368062832EFC9EF57FBD841958311B3DBD3BC4AC8FC421",
    "finance-v17/migrations/007_v17_oauth_foundation.sql": "A7D135CFD7DDA6F11A6D5A28317C24D7FB8B7476E73F70D3E0005BACFC5DD924",
    "finance-v17/migrations/008_v17_oauth_refresh.sql": "3B2D818B0BCEBA9C57CB882E149A546E781DEE7DCB21F6CE0C4E9E006B6B111A",
    "finance-v17/migrations/009_open_finance_foundation.sql": "F40BF2A455CAA70925C008EBC13CB9C36DBF4FB2CEE7AC309B3015C7F7975E72",
    "finance-v17/migrations/010_open_finance_coverage.sql": "4608C15B0977C166CDA3EC7112E20D67BDF091706AB2C8AD860930D2B02FEC9E",
    "finance-v17/requirements-deploy.txt": "7A375B056AD7AD462A5CB9C76C73CBDE0BB9AA1D0AF3C22275306DBFDB178DC6",
    "finance-v17/run.sh": "7FBDCE1C1A73A97AD757042956512D76BC3FB0DF6BDB023E17CB7F06BEC0B070",
    "finance-v17/src/finance_v2/PYTHON_REFERENCE_LICENSE.txt": "023163D4252112720E12757861BDD0272105EE1F67ED6A44130E652189A2F7AB",
    "finance-v17/src/finance_v2/UNICODE13_NOTICES.md": "86FCFFEA7F6E15385B93E7BB390CD44CD7BB65D05F672C68E8D556EE88679134",
    "finance-v17/src/finance_v2/UNICODE_DATA_LICENSE_2020.txt": "0EFACA9742A27A3F5A7F6F2B5C40A1D227295246E2483308BF83E05871FA202A",
    "finance-v17/src/finance_v2/UNICODE_LICENSE_V3.txt": "E7A93B009565CFCE55919A381437AC4DB883E9DA2126FA28B91D12732BC53D96",
    "finance-v17/src/finance_v2/__init__.py": "DAB0BAC240E6B17C1D405CAC702CF2DBF7D1B12D0819F83C297A3B986AC6D18C",
    "finance-v17/src/finance_v2/__main__.py": "E826BF61A5BD24948BADF5FC63E48E9EA442AFF1B59AAC8B2DB98AB986246E0C",
    "finance-v17/src/finance_v2/api.py": "7BAABF04D08B60D219FDED88B68CEFE3C75C78C7BB763B88FC6CF67A1C452D9A",
    "finance-v17/src/finance_v2/authorization.py": "ACA9BBCEF76A877FFF384D1D8667CE10136ACDC948F364F5AAB87F56440DF281",
    "finance-v17/src/finance_v2/config.py": "9A1E326203C57DDD37BE92650DE560BD500E2F110BC8D218FEEBDE57E33564DB",
    "finance-v17/src/finance_v2/db.py": "CC857220F0BEEE6B325DE7D0D8B2E4DCD41A712589BA0A092F2305F2695CE79B",
    "finance-v17/src/finance_v2/domain/__init__.py": "7169BA116BD572790380EEB6C760299DE48384F2A8AC0A9793D766C6ADA6947A",
    "finance-v17/src/finance_v2/domain/auto_debit.py": "B125DBE0E9257742E45C35EC0F78B83BEC339902ACE22911D06219214943B72A",
    "finance-v17/src/finance_v2/domain/automation.py": "35ED337F5722DA998567384511A9749A65731A7A4081DFF382A24609F64DF92B",
    "finance-v17/src/finance_v2/domain/calendar.py": "5957DFE49DE2EE7816E7A8E056F577238DF8394A62E07B2572B75E5B3ACE876C",
    "finance-v17/src/finance_v2/domain/catalog.py": "A2CB5A085AC6C40C98B600CEA658EBA60EB9CF388DBA02A42E7BA63E35BF6475",
    "finance-v17/src/finance_v2/domain/clock.py": "899CA93E36215E972C9AE69C0F25FE36FAF9C8ACE784F9C993C988AF89CAEF7E",
    "finance-v17/src/finance_v2/domain/errors.py": "3EEFB0319A087EE6DC704015A414FEF6108F48C5399BB80DF77CA9E3508BEF63",
    "finance-v17/src/finance_v2/domain/expenses.py": "F7736E1D41F60A87D89A3C13D72DBCF330AE4A0F7C9C38DD67BCD5B83DA5960D",
    "finance-v17/src/finance_v2/domain/idempotent.py": "1D33612240F097AE4E5D17C753C752539FA312D4D35918228788F12AC510B7CC",
    "finance-v17/src/finance_v2/domain/installments.py": "0ADB3291DD888A36A7CE4B7E994AA9FE998CE0489340324889A00CC62D0F4629",
    "finance-v17/src/finance_v2/domain/invoices.py": "1A8E93856E819AFB767B8E78C72B903893B5E0CCFF555383BE97EB974E74EC25",
    "finance-v17/src/finance_v2/domain/money.py": "FD54361DE33FC7AEC997F96BF710BA3D9FB3E3430DCDE258B226C1518387B20C",
    "finance-v17/src/finance_v2/domain/recurrence.py": "207353508E083627053909DB27105896A5F0F48A7E391FA0ED0A3920A8B2D997",
    "finance-v17/src/finance_v2/domain/recurrence_projection.py": "AAC80FE2933274E3DE304BE0B720F73795C7F9D814795E8F4E2E9B1C0D52BF35",
    "finance-v17/src/finance_v2/domain/reports.py": "356018EC24872B62ED1CA707B14DB62457743F70A9E6F2C61C795CCE035CDDE6",
    "finance-v17/src/finance_v2/domain/revenue_recurrence.py": "621F5F1C26CE55D6300021D8392A835688F5DCFF76BC229BEBC6DC282FF78D98",
    "finance-v17/src/finance_v2/domain/revenues.py": "A281B1EC600B3CB72E39452AE121B045841E426C8EF720DF4518558C7787AD0F",
    "finance-v17/src/finance_v2/domain/support.py": "7E29871207ECAADE1CB9460F95E8C4247CFE07A3D8519A2D14D04CFA1C080BE1",
    "finance-v17/src/finance_v2/ha_pluggy_options.py": "BC0EA17B452B4804739B2DC2B66FA252DE6CA47C338B530934511E1E7E7EF4FB",
    "finance-v17/src/finance_v2/http_runtime.py": "389EB8677365EC1656DAAD177DB86855D4644C873EB80B9BF39B93065DC52AA3",
    "finance-v17/src/finance_v2/idempotency.py": "137FE167853D2F7AA647CC0E9D5D1DB4CC1278F715102D015D962796536F33A2",
    "finance-v17/src/finance_v2/mcp_recurring.py": "CBC61BBF7A006B68A71146CC032733958DD9868B939768AD67C05A44DEFBE696",
    "finance-v17/src/finance_v2/migrations.py": "1C55B1376776C7E5DD076EC818EF84D1B1AEE23E1AD9D1967956EAAD28435281",
    "finance-v17/src/finance_v2/oauth.py": "723578407440DC5A452C42F6263E53ABF79A2E73B45BCC07A8A123002D484BF6",
    "finance-v17/src/finance_v2/oauth_server.py": "60513B9DACF531AA3117518165B9C6D0DE4D605C6C6E52151B672EC14B518DB1",
    "finance-v17/src/finance_v2/open_finance.py": "EA455DEBBDB8AC43DF66635539FFCEC6A8C726C50EA496FFD9EA46C6713EC74A",
    "finance-v17/src/finance_v2/open_finance_auto.py": "C380136C5E1D976C7994D2869FD563CBB809455B9DE32CFCBD47CFC8B7462AC3",
    "finance-v17/src/finance_v2/open_finance_coverage.py": "D4E4D2496D5C46B0CDC4AC12ADEE22D178702943B4527D748669730C54B572F3",
    "finance-v17/src/finance_v2/open_finance_diagnostics.py": "8B75668A8BAEB29AF8D62061F4193B4703EEF1342DF7A98DCE97C82E4BC51CFE",
    "finance-v17/src/finance_v2/open_finance_http.py": "929BBCF802CF7351FEA5BB14046FA597723F74CD8FD946A29E19D84C53031C0C",
    "finance-v17/src/finance_v2/open_finance_query.py": "F7786A5DAB271C1E2C25E4B14B9D764A7D36B899C8E2D0F79D9A962D5805857A",
    "finance-v17/src/finance_v2/pluggy_client.py": "078679A4ACFCA840C67EC43CE3718BEB1F2E6EF2B0889769AD673B669923C85F",
    "finance-v17/src/finance_v2/pluggy_config.py": "A47A76A55A77424179D4F1AF2EA93A39AA6367FFEE63A4E3DF76BF554FD3323C",
    "finance-v17/src/finance_v2/pluggy_coverage.py": "2A94A93584805E8CE9CAC052741730AB0E47ACCD5A32772E783C742CE4A54A7C",
    "finance-v17/src/finance_v2/pluggy_coverage_contracts.json": "985404C7EC53EFE9F97DC9A8591C444D974BF14CF414F8BADEE4840E798F6419",
    "finance-v17/src/finance_v2/scheduler/__init__.py": "0F6C705603CAB360E2322532134405A1F486A78B90DFD376DA33F5F8419ED54C",
    "finance-v17/src/finance_v2/scheduler/service.py": "9BBE1117A01E9A53FBB2BDB7691A082F4A1A0C9C6413E26082065D43260150FA",
    "finance-v17/src/finance_v2/unicode13_f06.py": "6C7EC1703A30FE81A9D577604DFC1B999D9AE48BF78B1318C20DE8E9662CBCD9",
    "finance-v17/src/finance_v2/unicode13_manifest.json": "9A279ACA79B09F3CE3C49EEA630619BED88115F416F81A97324093B4D856F07A",
    "finance-v17/src/finance_v2/unicode13_primitives.json": "DE81088662045384D1F0B07FDF53A40BEE297843782FE80BF1AAEA94383BAAA4",
    "finance-v17/src/finance_v2/web/app.js": "5AEF29B60A2FB99D2E07F93B7A7071BD4EF21D5F8D0A9F9350B90E666F83A51B",
    "finance-v17/src/finance_v2/web/capabilities.js": "74A7611FECFF5A8CCB55B2A065C162E54BBE5E9BF2CA02FF99E4EF3C100905B6",
    "finance-v17/src/finance_v2/web/completion.css": "A03B1C7195D7113F2BDF75E453879967CFA5A5183E12055D8C07CD100FCC8B73",
    "finance-v17/src/finance_v2/web/completion.js": "29F6AFA9D568FF4656E98F857D57001A741E9B2B3DE143B56AE3B1A34957E5BD",
    "finance-v17/src/finance_v2/web/forms.css": "2802E35BA26FE03463D93FBAD6BCCD9FC9F43C54ED19EE77C5F482E439CEC555",
    "finance-v17/src/finance_v2/web/icons.js": "6EAB9DA9EB654DBBA8B47564DC963D191340EA4431B716FEE73910002825077E",
    "finance-v17/src/finance_v2/web/index.html": "5F927A4D101CC95C2BBE08BAB1E6E189990C52982A7714814B0331B8294A8FE3",
    "finance-v17/src/finance_v2/web/open-finance-coverage.js": "EC48419FE090B2FD7BA14B512E669C7C8C3FDC2DA3D537673299048583447FB0",
    "finance-v17/src/finance_v2/web/open-finance-errors.js": "576A2E144FF32D09B925F2D500A6E3FFF6D661330605F7FF91B06A9E9DBB6D86",
    "finance-v17/src/finance_v2/web/open-finance.css": "F584CEE57B533F14EEDDC65FEA5AC4C71A807A123467333E5F124C2303923283",
    "finance-v17/src/finance_v2/web/open-finance.js": "B742ED50D85FFC911B7D8D51B9111E94946CF203A11560409CA954B81E7FCC42",
    "finance-v17/src/finance_v2/web/presentation.js": "BED2EE2C3B3F57FA91A21AEC11BCCCD47D58FA1BD6CC5F996097F0F9FAD9DA2A",
    "finance-v17/src/finance_v2/web/privacy.css": "315E53E0F4E7DF96D47D94BF15D7645A83023BB7747D3E0444A8B9C00B47ECA1",
    "finance-v17/src/finance_v2/web/privacy.js": "2D6BFB4F89BFED54F29BD453C1E9FA8C77B6613993788336D1633D54D98F8999",
    "finance-v17/src/finance_v2/web/revenues.js": "9626603D886EF025CE1BD41791D86066473F447A1F0A97839401DB0C994F040A",
    "finance-v17/src/finance_v2/web/styles.css": "9CA8179C66C19C1D4044D0644CDC1F9D1E071EA72C01E20B283A1FD8AAA6DD46",
    "finance-v17/src/finance_v2/web/unlock.html": "B2BE8B6548E357888C13EB4AB7F788EDEE66604798C71D27FB91E0700BBA79A5"
  }
}

```

## Imagem final após correção da resposta de progresso tardia

```text
#0 building with "desktop-linux" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 924B done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#2 DONE 0.0s

#3 [internal] load .dockerignore
#3 transferring context: 90B done
#3 DONE 0.0s

#4 [1/9] FROM docker.io/library/python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
#4 DONE 0.0s

#5 [internal] load build context
#5 transferring context: 16.08kB done
#5 DONE 0.0s

#6 [2/9] WORKDIR /opt/finance-v2
#6 CACHED

#7 [3/9] COPY requirements-deploy.txt ./
#7 CACHED

#8 [4/9] RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt     && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2
#8 CACHED

#9 [5/9] COPY --chown=financev2:financev2 src ./src
#9 DONE 0.0s

#10 [6/9] COPY --chown=financev2:financev2 migrations ./migrations
#10 DONE 0.0s

#11 [7/9] COPY --chown=financev2:financev2 run.sh ./run.sh
#11 DONE 0.0s

#12 [8/9] COPY --chown=financev2:financev2 migrate.sh ./migrate.sh
#12 DONE 0.0s

#13 [9/9] RUN chmod 0755 /opt/finance-v2/run.sh /opt/finance-v2/migrate.sh
#13 DONE 0.3s

#14 exporting to image
#14 exporting layers 0.1s done
#14 writing image sha256:b23ed43e4e897e1574b70fb037d6f882d3b3d65a23c0185f931c1a1d2bcea8db done
#14 naming to docker.io/library/finance-v17-d08:0.1.26-open-finance.1-arm64 done
#14 DONE 0.1s

View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/pwt9077xpyevmrxneh1crymxr

```

## Pacote determinístico

Dois builds ZIP em memória byte-idênticos; CRC de todos os membros PASS; 87 membros comparados byte a byte; 8 protegidos PASS. Manifesto de release próprio interno MANIFEST.sha256.json; manifestos históricos inalterados.

SHA-256: `E0CE9C07D312ED9958AB747E9B002AF720BB3DAFC9F0C7035645B7F48B6EAD8B`

## Operação da imagem FINAL

Imagem: `sha256:b23ed43e4e897e1574b70fb037d6f882d3b3d65a23c0185f931c1a1d2bcea8db`

```text
{"image_files_verified": 80, "architecture": "aarch64"}
test_auth_401_never_retries_or_exposes_provider_body (__main__.AuthTests.test_auth_401_never_retries_or_exposes_provider_body) ... ok
test_bank_context_and_cache_are_not_shared (__main__.AuthTests.test_bank_context_and_cache_are_not_shared) ... ok
test_cache_expiry_boundary_and_request_body (__main__.AuthTests.test_cache_expiry_boundary_and_request_body) ... ok
test_concurrent_cache_acquisition_is_single_flight (__main__.AuthTests.test_concurrent_cache_acquisition_is_single_flight) ... ok
test_invalid_auth_response_does_not_enter_cache (__main__.AuthTests.test_invalid_auth_response_does_not_enter_cache) ... ok
test_late_coverage_401_does_not_discard_new_key (__main__.AuthTests.test_late_coverage_401_does_not_discard_new_key) ... ok
test_one_renewal_then_stop_on_repeated_401 (__main__.AuthTests.test_one_renewal_then_stop_on_repeated_401) ... ok
test_optional_403_does_not_authenticate_again (__main__.AuthTests.test_optional_403_does_not_authenticate_again) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.053s

OK
{"case": "ARM64_wrapper_TERM", "exit_code": 0, "ready_seconds": 34.078, "shutdown_seconds": 2.547, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}
{"case": "ARM64_wrapper_INT", "exit_code": 0, "ready_seconds": 33.094, "shutdown_seconds": 2.078, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}
{"owned_containers_removed": 4, "host_mounts": 0, "real_requests": 0}
{"result": "PASS", "cases": [{"case": "ARM64_auth", "pass": 8}, {"case": "ARM64_wrapper_TERM", "exit_code": 0, "ready_seconds": 34.078, "shutdown_seconds": 2.547, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}, {"case": "ARM64_wrapper_INT", "exit_code": 0, "ready_seconds": 33.094, "shutdown_seconds": 2.078, "schema": 10, "integrity": "ok", "fk_violations": 0, "pid_after": 0}]}

```

## Regressão histórica de interface (fontes externas somente leitura)

```text
{
  "pass_count": 3,
  "fail_count": 0,
  "tests": [
    {
      "test": "test_state_actions_svg_and_controller_refresh_payloads",
      "status": "PASS",
      "exit_code": 0,
      "original_sha256": "F17402A89DC4AAD45C4A43207AD35D48338A8605A4AFFD86F859E80A63F1C183",
      "executed_js_sha256": "BCFACA1155EB8D2F880FD1C3E4A92A38D1808FC7461D90FE3FE83EACCDF98774",
      "assertions_changed": false
    },
    {
      "test": "test_human_audit_error_and_interface_contracts",
      "status": "PASS",
      "exit_code": 0,
      "original_sha256": "A04C01F9F681C27DBAE8298BA8A62EC40E11B4587AC5C5C7BA095ECC01EC57A0",
      "executed_js_sha256": "38EE1FB9C1082D4169E8AD3A1C2246988EE918C01670E95CCD405748F00AABFC",
      "assertions_changed": false
    },
    {
      "test": "test_indicator_computed_layout_and_accessibility_in_browser",
      "status": "PASS",
      "exit_code": 0,
      "original_sha256": "080EB92CD366F58814020EA623782103BFEEBDB7C1DE3E9B70C2F57EA998ED0C",
      "executed_js_sha256": "2C7E0F61490BF3399349D2195831AC3D002A4E76FCCF0D36D63C4400D78391C4",
      "assertions_changed": false
    }
  ],
  "database_access": false,
  "migrations_executed": false
}

```

## Resumo final (somente rodadas finais, falhas iniciais preservadas acima)

| Suíte | PASS | FAIL | ERROR | SKIP |
|---|---:|---:|---:|---:|
| Open Finance / SQLite / workers / D02 + fronteira de fixtures Windows | 93 | 0 | 0 | 0 |
| Domínio financeiro / receitas / scheduler + fronteira Windows | 48 | 0 | 0 | 0 |
| MCP | 6 | 0 | 0 | 0 |
| D08 auth Windows | 8 | 0 | 0 | 0 |
| D08 interface Node final | 7 | 0 | 0 | 0 |
| Interface histórica | 3 | 0 | 0 | 0 |
| D08 auth ARM64 final | 8 | 0 | 0 | 0 |
| Wrapper real ARM64 final TERM/INT | 2 | 0 | 0 | 0 |

175 execuções de casos finais somando grupos/plataformas, não 175 comportamentos únicos. Os três controles de fronteira são executados em ambos os grupos Windows. Adicionalmente: build final PASS, correspondência de 80 arquivos na imagem PASS, oito hashes protegidos PASS, três controles negativos de integridade PASS e ZIP determinístico/CRC PASS.

Os 8 casos Windows D08 auth foram executados por `python -B candidate/tests/test_d08_auth.py`; todos passaram em 0,004 s após corrigir o 401 tardio. A suíte Node final `node --test candidate/tests/test_d08_ui.mjs` passou 7/7 em 103,95 ms após corrigir o progresso atrasado. Os resultados anteriores FAIL continuam registrados e não contam como aprovação.

Uma tentativa de imprimir o resultado Node no console Python cp1252 encontrou UnicodeEncodeError para o símbolo de aprovação; o log UTF-8 já havia sido gravado integralmente antes dessa impressão. Isso não altera os resultados de teste preservados.

As duas execuções de imagem removeram somente seus quatro contêineres próprios cada; nenhum host mount, nenhuma porta publicada, zero requisições bancárias. Bancos Windows usaram TemporaryDirectory removido ao sair; bancos Docker ficaram em tmpfs descartado com os contêineres. A imagem candidata final permanece como artefato local. Supervisor e serviços reais: NOT_PERFORMED.

Conferência final: 131 fontes históricas D03 inalteradas; oito protegidos da candidata inalterados; ZIP corresponde aos fontes atuais; nenhum arquivo de banco ou configuração real incluído.
