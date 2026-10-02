PRAGMA foreign_keys=ON;

CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)));
CREATE TABLE categories(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL CHECK(active IN(0,1)));
CREATE TABLE tags(id INTEGER PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL CHECK(active IN(0,1)));

CREATE TABLE cards(
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN(0,1)),
 invoice_payment_mode TEXT NOT NULL CHECK(invoice_payment_mode IN('MANUAL','AUTO_DEBIT')),
 invoice_payment_account_id INTEGER REFERENCES accounts(id),
 CHECK((invoice_payment_mode='MANUAL' AND invoice_payment_account_id IS NULL) OR
       (invoice_payment_mode='AUTO_DEBIT' AND invoice_payment_account_id IS NOT NULL))
);

CREATE TABLE card_calendar_versions(
 id INTEGER PRIMARY KEY,card_id INTEGER NOT NULL REFERENCES cards(id),
 effective_from TEXT NOT NULL,effective_to TEXT,closing_day INTEGER NOT NULL CHECK(closing_day BETWEEN 1 AND 31),
 due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),
 CHECK(date(effective_from,'+0 days') IS NOT NULL AND effective_from=date(effective_from,'+0 days')),
 CHECK(effective_to IS NULL OR (date(effective_to,'+0 days') IS NOT NULL AND effective_to=date(effective_to,'+0 days'))),
 CHECK(effective_to IS NULL OR effective_to>=effective_from)
);

CREATE TABLE recurring_series(
 id INTEGER PRIMARY KEY,lineage_epoch_uuid TEXT NOT NULL UNIQUE CHECK(length(trim(lineage_epoch_uuid))>0),
 start_date TEXT NOT NULL,end_date TEXT,ended_at TEXT,reconciled_through TEXT,
 CHECK(date(start_date,'+0 days') IS NOT NULL AND start_date=date(start_date,'+0 days')),
 CHECK(end_date IS NULL OR (date(end_date,'+0 days') IS NOT NULL AND end_date=date(end_date,'+0 days'))),
 CHECK(end_date IS NULL OR end_date>=start_date),
 CHECK(ended_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',ended_at) IS NOT NULL AND ended_at=strftime('%Y-%m-%dT%H:%M:%SZ',ended_at,'+0 seconds'))),
 CHECK(reconciled_through IS NULL OR (date(reconciled_through,'+0 days') IS NOT NULL AND reconciled_through=date(reconciled_through,'+0 days')))
);

CREATE TABLE recurring_series_versions(
 id INTEGER PRIMARY KEY,recurring_series_id INTEGER NOT NULL REFERENCES recurring_series(id),
 lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN('ACTIVE','SUPERSEDED')),
 description TEXT NOT NULL CHECK(length(trim(description))>0),category_id INTEGER NOT NULL REFERENCES categories(id),
 superseded_at TEXT,superseded_by_version_id INTEGER REFERENCES recurring_series_versions(id),supersession_reason_code TEXT CHECK(supersession_reason_code IS NULL OR length(trim(supersession_reason_code))>0),supersession_correlation_id TEXT CHECK(supersession_correlation_id IS NULL OR length(trim(supersession_correlation_id))>0),created_at TEXT NOT NULL,
 effective_from TEXT NOT NULL,effective_to TEXT,anchor_occurrence_key TEXT NOT NULL CHECK(length(trim(anchor_occurrence_key))>0),anchor_logical_date TEXT NOT NULL,
 anchor_logical_ordinal INTEGER NOT NULL CHECK(anchor_logical_ordinal>=0),
 frequency TEXT NOT NULL CHECK(frequency IN('WEEKLY','BIWEEKLY','MONTHLY','BIMONTHLY','QUARTERLY','SEMIANNUAL','ANNUAL')),
 base_day INTEGER,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 planned_payment_method TEXT NOT NULL CHECK(planned_payment_method IN('PIX','DEBIT','CASH','BANK_SLIP','AUTO_DEBIT','CREDIT_CARD')),
 account_id INTEGER REFERENCES accounts(id),card_id INTEGER REFERENCES cards(id),
 due_rule TEXT NOT NULL CHECK(due_rule IN('SAME_DAY','OFFSET','DAY_OF_MONTH','INVOICE')),
 due_offset_days INTEGER,due_day INTEGER,
 CHECK(date(effective_from,'+0 days') IS NOT NULL AND effective_from=date(effective_from,'+0 days')),
 CHECK(effective_to IS NULL OR (date(effective_to,'+0 days') IS NOT NULL AND effective_to=date(effective_to,'+0 days'))),
 CHECK(date(anchor_logical_date,'+0 days') IS NOT NULL AND anchor_logical_date=date(anchor_logical_date,'+0 days')),
 CHECK(effective_to IS NULL OR effective_to>=effective_from),
 CHECK((frequency IN('WEEKLY','BIWEEKLY') AND base_day IS NULL) OR
       (frequency IN('MONTHLY','BIMONTHLY','QUARTERLY','SEMIANNUAL','ANNUAL') AND base_day IS NOT NULL AND base_day BETWEEN 1 AND 31)),
 CHECK((planned_payment_method='CREDIT_CARD' AND card_id IS NOT NULL AND account_id IS NULL AND due_rule='INVOICE') OR
       (planned_payment_method IN('PIX','DEBIT','AUTO_DEBIT') AND card_id IS NULL AND account_id IS NOT NULL AND due_rule<>'INVOICE') OR
       (planned_payment_method='CASH' AND card_id IS NULL AND account_id IS NULL AND due_rule<>'INVOICE') OR
       (planned_payment_method='BANK_SLIP' AND card_id IS NULL AND due_rule<>'INVOICE')),
 CHECK((due_rule='SAME_DAY' AND due_offset_days IS NULL AND due_day IS NULL) OR
       (due_rule='OFFSET' AND due_offset_days IS NOT NULL AND due_offset_days>=0 AND due_day IS NULL) OR
       (due_rule='DAY_OF_MONTH' AND due_day IS NOT NULL AND due_day BETWEEN 1 AND 31 AND due_offset_days IS NULL) OR
       (due_rule='INVOICE' AND due_offset_days IS NULL AND due_day IS NULL)),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK((lifecycle_state='ACTIVE' AND superseded_at IS NULL AND superseded_by_version_id IS NULL AND supersession_reason_code IS NULL AND supersession_correlation_id IS NULL) OR
       (lifecycle_state='SUPERSEDED' AND superseded_at IS NOT NULL AND superseded_by_version_id IS NOT NULL AND supersession_reason_code IS NOT NULL AND supersession_correlation_id IS NOT NULL)),
 CHECK(superseded_by_version_id IS NULL OR superseded_by_version_id<>id),
 CHECK(superseded_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at) IS NOT NULL AND superseded_at=strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at,'+0 seconds')))
);

CREATE TABLE recurring_version_tags(recurring_version_id INTEGER NOT NULL REFERENCES recurring_series_versions(id),tag_id INTEGER NOT NULL REFERENCES tags(id),PRIMARY KEY(recurring_version_id,tag_id));

CREATE TABLE installment_series(
 id INTEGER PRIMARY KEY,purchase_date TEXT NOT NULL,card_id INTEGER NOT NULL REFERENCES cards(id),
 original_total_cents INTEGER NOT NULL CHECK(original_total_cents>0),
 installment_count INTEGER NOT NULL CHECK(installment_count>0),ended_from_installment INTEGER,ended_at TEXT,
 CHECK(date(purchase_date,'+0 days') IS NOT NULL AND purchase_date=date(purchase_date,'+0 days')),
 CHECK(ended_from_installment IS NULL OR ended_from_installment BETWEEN 1 AND installment_count),
 CHECK(ended_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',ended_at) IS NOT NULL AND ended_at=strftime('%Y-%m-%dT%H:%M:%SZ',ended_at,'+0 seconds')))
);

CREATE TABLE invoices(
 id INTEGER PRIMARY KEY,card_id INTEGER NOT NULL REFERENCES cards(id),closing_date TEXT NOT NULL,due_date TEXT NOT NULL,
 period_start TEXT NOT NULL,period_end TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN('OPEN','CLOSED','PAID','CANCELLED')),
 closed_total_cents INTEGER CHECK(closed_total_cents IS NULL OR closed_total_cents>=0),
 payment_mode TEXT NOT NULL CHECK(payment_mode IN('MANUAL','AUTO_DEBIT')),payment_account_id INTEGER REFERENCES accounts(id),
 created_at TEXT NOT NULL,closed_at TEXT,paid_at TEXT,cancelled_at TEXT,
 CHECK(date(closing_date,'+0 days') IS NOT NULL AND closing_date=date(closing_date,'+0 days')),CHECK(date(due_date,'+0 days') IS NOT NULL AND due_date=date(due_date,'+0 days')),
 CHECK(date(period_start,'+0 days') IS NOT NULL AND period_start=date(period_start,'+0 days')),CHECK(date(period_end,'+0 days') IS NOT NULL AND period_end=date(period_end,'+0 days')),
 CHECK(period_start<=period_end),CHECK(period_end=closing_date),CHECK(due_date>closing_date),
 CHECK((payment_mode='MANUAL' AND payment_account_id IS NULL) OR (payment_mode='AUTO_DEBIT' AND payment_account_id IS NOT NULL)),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK(closed_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',closed_at) IS NOT NULL AND closed_at=strftime('%Y-%m-%dT%H:%M:%SZ',closed_at,'+0 seconds'))),
 CHECK(paid_at IS NULL OR (date(paid_at,'+0 days') IS NOT NULL AND paid_at=date(paid_at,'+0 days'))),
 CHECK(cancelled_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',cancelled_at) IS NOT NULL AND cancelled_at=strftime('%Y-%m-%dT%H:%M:%SZ',cancelled_at,'+0 seconds'))),
 CHECK((state='OPEN' AND closed_at IS NULL AND paid_at IS NULL AND cancelled_at IS NULL) OR
       (state='CLOSED' AND closed_at IS NOT NULL AND paid_at IS NULL AND cancelled_at IS NULL) OR
       (state='PAID' AND closed_at IS NOT NULL AND paid_at IS NOT NULL AND cancelled_at IS NULL) OR
       (state='CANCELLED' AND paid_at IS NULL AND cancelled_at IS NOT NULL)),
 CHECK(state<>'OPEN' OR closed_total_cents IS NULL),
 CHECK(state NOT IN('CLOSED','PAID') OR closed_total_cents IS NOT NULL),
 CHECK(state<>'CANCELLED' OR ((closed_at IS NULL AND closed_total_cents IS NULL) OR (closed_at IS NOT NULL AND closed_total_cents IS NOT NULL))),
 UNIQUE(card_id,closing_date)
);

CREATE TABLE invoice_total_revisions(
 id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),previous_total_cents INTEGER NOT NULL CHECK(previous_total_cents>=0),
 new_total_cents INTEGER NOT NULL CHECK(new_total_cents>=0),reason_code TEXT NOT NULL CHECK(length(trim(reason_code))>0),
 correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),actor TEXT NOT NULL CHECK(length(trim(actor))>0),created_at TEXT NOT NULL,
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds'))
);

CREATE TABLE expenses(
 id INTEGER PRIMARY KEY,description TEXT NOT NULL CHECK(length(trim(description))>0),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),expense_date TEXT NOT NULL,due_date TEXT,
 planned_payment_method TEXT NOT NULL CHECK(planned_payment_method IN('PIX','DEBIT','CASH','BANK_SLIP','AUTO_DEBIT','CREDIT_CARD')),
 category_id INTEGER NOT NULL REFERENCES categories(id),account_id INTEGER REFERENCES accounts(id),card_id INTEGER REFERENCES cards(id),
 invoice_id INTEGER REFERENCES invoices(id),recurring_series_id INTEGER REFERENCES recurring_series(id),
 recurring_version_id INTEGER REFERENCES recurring_series_versions(id),recurrence_occurrence_key TEXT,logical_slot_lineage_key TEXT,
 materialization_slot_key TEXT,installment_series_id INTEGER REFERENCES installment_series(id),installment_number INTEGER,
 lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN('ACTIVE','CANCELLED','SUPERSEDED')),
 superseded_at TEXT,superseded_by_expense_id INTEGER REFERENCES expenses(id),supersession_reason_code TEXT CHECK(supersession_reason_code IS NULL OR length(trim(supersession_reason_code))>0),supersession_correlation_id TEXT CHECK(supersession_correlation_id IS NULL OR length(trim(supersession_correlation_id))>0),
 notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 CHECK(date(expense_date,'+0 days') IS NOT NULL AND expense_date=date(expense_date,'+0 days')),CHECK(due_date IS NULL OR (date(due_date,'+0 days') IS NOT NULL AND due_date=date(due_date,'+0 days'))),
 CHECK((planned_payment_method='CREDIT_CARD' AND card_id IS NOT NULL AND invoice_id IS NOT NULL AND account_id IS NULL AND due_date IS NULL) OR
       (planned_payment_method IN('PIX','DEBIT','AUTO_DEBIT') AND card_id IS NULL AND invoice_id IS NULL AND account_id IS NOT NULL) OR
       (planned_payment_method='CASH' AND card_id IS NULL AND invoice_id IS NULL AND account_id IS NULL) OR
       (planned_payment_method='BANK_SLIP' AND card_id IS NULL AND invoice_id IS NULL)),
 CHECK(NOT(recurring_series_id IS NOT NULL AND installment_series_id IS NOT NULL)),
 CHECK((recurring_series_id IS NULL AND recurring_version_id IS NULL AND recurrence_occurrence_key IS NULL AND logical_slot_lineage_key IS NULL AND materialization_slot_key IS NULL) OR
       (recurring_series_id IS NOT NULL AND recurring_version_id IS NOT NULL AND recurrence_occurrence_key IS NOT NULL AND logical_slot_lineage_key IS NOT NULL AND materialization_slot_key IS NOT NULL)),
 CHECK((installment_series_id IS NULL AND installment_number IS NULL) OR
       (installment_series_id IS NOT NULL AND installment_number IS NOT NULL AND installment_number>=1)),
 CHECK(recurring_series_id IS NULL OR (length(trim(recurrence_occurrence_key))>0 AND length(trim(logical_slot_lineage_key))>0 AND length(trim(materialization_slot_key))>0)),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',updated_at) IS NOT NULL AND updated_at=strftime('%Y-%m-%dT%H:%M:%SZ',updated_at,'+0 seconds')),
 CHECK(superseded_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at) IS NOT NULL AND superseded_at=strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at,'+0 seconds'))),
 CHECK(superseded_by_expense_id IS NULL OR superseded_by_expense_id<>id),
 CHECK((lifecycle_state IN('ACTIVE','CANCELLED') AND superseded_at IS NULL AND superseded_by_expense_id IS NULL AND supersession_reason_code IS NULL AND supersession_correlation_id IS NULL) OR
       (lifecycle_state='SUPERSEDED' AND superseded_at IS NOT NULL AND superseded_by_expense_id IS NOT NULL AND supersession_reason_code IS NOT NULL AND supersession_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_installment ON expenses(installment_series_id,installment_number) WHERE installment_series_id IS NOT NULL;

CREATE TABLE expense_tags(expense_id INTEGER NOT NULL REFERENCES expenses(id),tag_id INTEGER NOT NULL REFERENCES tags(id),PRIMARY KEY(expense_id,tag_id));
CREATE TABLE occurrence_overrides(
 id INTEGER PRIMARY KEY,expense_id INTEGER NOT NULL REFERENCES expenses(id),originating_recurring_version_id INTEGER NOT NULL REFERENCES recurring_series_versions(id),
 reason_code TEXT NOT NULL CHECK(length(trim(reason_code))>0),correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),
 created_at TEXT NOT NULL,created_by_actor TEXT NOT NULL CHECK(length(trim(created_by_actor))>0),
 removed_at TEXT,removed_by_actor TEXT CHECK(removed_by_actor IS NULL OR length(trim(removed_by_actor))>0),
 removal_reason_code TEXT CHECK(removal_reason_code IS NULL OR length(trim(removal_reason_code))>0),
 removal_correlation_id TEXT CHECK(removal_correlation_id IS NULL OR length(trim(removal_correlation_id))>0),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK(removed_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',removed_at) IS NOT NULL AND removed_at=strftime('%Y-%m-%dT%H:%M:%SZ',removed_at,'+0 seconds'))),
 CHECK((removed_at IS NULL AND removed_by_actor IS NULL AND removal_reason_code IS NULL AND removal_correlation_id IS NULL) OR
       (removed_at IS NOT NULL AND removed_by_actor IS NOT NULL AND removal_reason_code IS NOT NULL AND removal_correlation_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_override_active ON occurrence_overrides(expense_id) WHERE removed_at IS NULL;

CREATE TABLE recurrence_slot_resolutions(
 id INTEGER PRIMARY KEY,recurring_series_id INTEGER NOT NULL REFERENCES recurring_series(id),recurring_version_id INTEGER NOT NULL REFERENCES recurring_series_versions(id),
 materialization_slot_key TEXT NOT NULL CHECK(length(trim(materialization_slot_key))>0),logical_slot_lineage_key TEXT NOT NULL CHECK(length(trim(logical_slot_lineage_key))>0),logical_ordinal INTEGER NOT NULL CHECK(logical_ordinal>=0),
 logical_occurrence_date TEXT NOT NULL,resolution TEXT NOT NULL CHECK(resolution IN('CREATED','RESERVED_PROTECTED','SUPPRESSED')),
 resolution_state TEXT NOT NULL CHECK(resolution_state IN('ACTIVE','SUPERSEDED')),
 reason_code TEXT NOT NULL CHECK(length(trim(reason_code))>0),correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),
 superseded_at TEXT,superseded_by_resolution_id INTEGER REFERENCES recurrence_slot_resolutions(id),created_at TEXT NOT NULL,expense_id INTEGER REFERENCES expenses(id),protected_expense_id INTEGER REFERENCES expenses(id),
 CHECK(date(logical_occurrence_date,'+0 days') IS NOT NULL AND logical_occurrence_date=date(logical_occurrence_date,'+0 days')),
 CHECK((resolution='CREATED' AND expense_id IS NOT NULL AND protected_expense_id IS NULL) OR
       (resolution='RESERVED_PROTECTED' AND protected_expense_id IS NOT NULL AND expense_id IS NULL) OR
       (resolution='SUPPRESSED' AND expense_id IS NULL AND protected_expense_id IS NULL)),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK((resolution_state='ACTIVE' AND superseded_at IS NULL AND superseded_by_resolution_id IS NULL) OR
       (resolution_state='SUPERSEDED' AND superseded_at IS NOT NULL AND superseded_by_resolution_id IS NOT NULL)),
 CHECK(superseded_by_resolution_id IS NULL OR superseded_by_resolution_id<>id),
 CHECK(superseded_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at) IS NOT NULL AND superseded_at=strftime('%Y-%m-%dT%H:%M:%SZ',superseded_at,'+0 seconds')))
);
CREATE UNIQUE INDEX ux_slot_lineage ON recurrence_slot_resolutions(recurring_series_id,logical_slot_lineage_key) WHERE resolution_state='ACTIVE';
CREATE UNIQUE INDEX ux_slot_material ON recurrence_slot_resolutions(recurring_series_id,recurring_version_id,materialization_slot_key) WHERE resolution_state='ACTIVE';

CREATE TABLE settlements(
 id INTEGER PRIMARY KEY,settlement_key TEXT NOT NULL UNIQUE CHECK(length(trim(settlement_key))>0),
 obligation_type TEXT NOT NULL CHECK(obligation_type IN('EXPENSE','INVOICE')),obligation_id INTEGER NOT NULL,
 supersedes_settlement_id INTEGER REFERENCES settlements(id),created_at TEXT NOT NULL,actor TEXT NOT NULL CHECK(length(trim(actor))>0),
 CHECK(supersedes_settlement_id IS NULL OR supersedes_settlement_id<>id),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds'))
);
CREATE UNIQUE INDEX ux_settlement_successor ON settlements(supersedes_settlement_id) WHERE supersedes_settlement_id IS NOT NULL;

CREATE TABLE expense_payments(
 id INTEGER PRIMARY KEY,expense_id INTEGER NOT NULL REFERENCES expenses(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),paid_on TEXT NOT NULL,
 payment_method TEXT NOT NULL CHECK(payment_method IN('PIX','DEBIT','BANK_TRANSFER','CASH','AUTO_DEBIT')),account_id INTEGER REFERENCES accounts(id),
 source TEXT NOT NULL CHECK(source IN('MANUAL','AUTOMATIC')),settlement_id INTEGER REFERENCES settlements(id),
 reversed_at TEXT,reversed_on TEXT,reversed_by_actor TEXT,reversal_reason TEXT,replacement_payment_id INTEGER REFERENCES expense_payments(id),correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),
 CHECK(date(paid_on,'+0 days') IS NOT NULL AND paid_on=date(paid_on,'+0 days')),CHECK(reversed_on IS NULL OR (date(reversed_on,'+0 days') IS NOT NULL AND reversed_on=date(reversed_on,'+0 days'))),
 CHECK(reversed_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',reversed_at) IS NOT NULL AND reversed_at=strftime('%Y-%m-%dT%H:%M:%SZ',reversed_at,'+0 seconds'))),
 CHECK((reversed_at IS NULL AND reversed_on IS NULL AND reversed_by_actor IS NULL AND reversal_reason IS NULL) OR
       (reversed_at IS NOT NULL AND reversed_on IS NOT NULL AND reversed_by_actor IS NOT NULL AND reversal_reason IS NOT NULL)),
 CHECK(reversed_by_actor IS NULL OR length(trim(reversed_by_actor))>0),CHECK(reversal_reason IS NULL OR length(trim(reversal_reason))>0),
 CHECK(reversed_on IS NULL OR reversed_on>=paid_on),CHECK(replacement_payment_id IS NULL OR replacement_payment_id<>id),
 CHECK((source='AUTOMATIC' AND payment_method='AUTO_DEBIT' AND settlement_id IS NOT NULL AND account_id IS NOT NULL) OR
       (source='MANUAL' AND payment_method<>'AUTO_DEBIT' AND settlement_id IS NULL)),
 CHECK((payment_method IN('PIX','DEBIT','BANK_TRANSFER') AND account_id IS NOT NULL) OR (payment_method='CASH' AND account_id IS NULL) OR payment_method='AUTO_DEBIT')
);
CREATE UNIQUE INDEX ux_ep_active_expense ON expense_payments(expense_id) WHERE reversed_at IS NULL;
CREATE UNIQUE INDEX ux_ep_settlement ON expense_payments(settlement_id) WHERE settlement_id IS NOT NULL;
CREATE UNIQUE INDEX ux_ep_replacement ON expense_payments(replacement_payment_id) WHERE replacement_payment_id IS NOT NULL;

CREATE TABLE invoice_payments(
 id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),paid_on TEXT NOT NULL,
 payment_method TEXT NOT NULL CHECK(payment_method IN('PIX','DEBIT','BANK_TRANSFER','AUTO_DEBIT')),account_id INTEGER NOT NULL REFERENCES accounts(id),
 source TEXT NOT NULL CHECK(source IN('MANUAL','AUTOMATIC')),settlement_id INTEGER REFERENCES settlements(id),
 reversed_at TEXT,reversed_on TEXT,reversed_by_actor TEXT,reversal_reason TEXT,replacement_payment_id INTEGER REFERENCES invoice_payments(id),correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),
 CHECK(date(paid_on,'+0 days') IS NOT NULL AND paid_on=date(paid_on,'+0 days')),CHECK(reversed_on IS NULL OR (date(reversed_on,'+0 days') IS NOT NULL AND reversed_on=date(reversed_on,'+0 days'))),
 CHECK(reversed_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',reversed_at) IS NOT NULL AND reversed_at=strftime('%Y-%m-%dT%H:%M:%SZ',reversed_at,'+0 seconds'))),
 CHECK((reversed_at IS NULL AND reversed_on IS NULL AND reversed_by_actor IS NULL AND reversal_reason IS NULL) OR
       (reversed_at IS NOT NULL AND reversed_on IS NOT NULL AND reversed_by_actor IS NOT NULL AND reversal_reason IS NOT NULL)),
 CHECK(reversed_by_actor IS NULL OR length(trim(reversed_by_actor))>0),CHECK(reversal_reason IS NULL OR length(trim(reversal_reason))>0),
 CHECK(reversed_on IS NULL OR reversed_on>=paid_on),CHECK(replacement_payment_id IS NULL OR replacement_payment_id<>id),
 CHECK((source='AUTOMATIC' AND payment_method='AUTO_DEBIT' AND settlement_id IS NOT NULL) OR
       (source='MANUAL' AND payment_method<>'AUTO_DEBIT' AND settlement_id IS NULL))
);
CREATE UNIQUE INDEX ux_ip_settlement ON invoice_payments(settlement_id) WHERE settlement_id IS NOT NULL;
CREATE UNIQUE INDEX ux_ip_replacement ON invoice_payments(replacement_payment_id) WHERE replacement_payment_id IS NOT NULL;

CREATE TABLE automation_executions(
 id INTEGER PRIMARY KEY,settlement_id INTEGER NOT NULL REFERENCES settlements(id),attempt_group_key TEXT NOT NULL CHECK(length(trim(attempt_group_key))>0),
 attempt_number INTEGER NOT NULL CHECK(attempt_number>0),result TEXT NOT NULL CHECK(result IN('SUCCESS','RETRYABLE_FAILURE','REQUIRES_ATTENTION','SKIPPED')),
 started_at TEXT NOT NULL,finished_at TEXT NOT NULL,error_code TEXT,
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',started_at) IS NOT NULL AND started_at=strftime('%Y-%m-%dT%H:%M:%SZ',started_at,'+0 seconds')),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',finished_at) IS NOT NULL AND finished_at=strftime('%Y-%m-%dT%H:%M:%SZ',finished_at,'+0 seconds')),
 CHECK(finished_at>=started_at),
 CHECK((result IN('SUCCESS','SKIPPED') AND error_code IS NULL) OR
       (result IN('RETRYABLE_FAILURE','REQUIRES_ATTENTION') AND error_code IS NOT NULL AND length(trim(error_code))>0)),
 UNIQUE(settlement_id,attempt_group_key,attempt_number)
);
CREATE UNIQUE INDEX ux_auto_success ON automation_executions(settlement_id) WHERE result='SUCCESS';

CREATE TABLE idempotency_records(
 id INTEGER PRIMARY KEY,client_id TEXT NOT NULL,operation TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN('IN_PROGRESS','COMPLETED')),response_json TEXT,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,completed_at TEXT,
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',expires_at) IS NOT NULL AND expires_at=strftime('%Y-%m-%dT%H:%M:%SZ',expires_at,'+0 seconds')),
 CHECK(completed_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',completed_at) IS NOT NULL AND completed_at=strftime('%Y-%m-%dT%H:%M:%SZ',completed_at,'+0 seconds'))),
 CHECK(length(trim(client_id))>0 AND length(trim(operation))>0 AND length(trim(idempotency_key))>0 AND length(trim(request_hash))>0),
 CHECK(julianday(expires_at)>=julianday(created_at)+90),
 CHECK((state='IN_PROGRESS' AND completed_at IS NULL AND response_json IS NULL) OR (state='COMPLETED' AND completed_at IS NOT NULL AND response_json IS NOT NULL)),
 UNIQUE(client_id,operation,idempotency_key)
);

CREATE TABLE permanent_operation_keys(
 id INTEGER PRIMARY KEY,client_id TEXT NOT NULL,operation TEXT NOT NULL,operation_key TEXT NOT NULL CHECK(length(trim(operation_key))>0),
 request_hash TEXT NOT NULL,resource_type TEXT NOT NULL,resource_id INTEGER NOT NULL,correlation_id TEXT,created_at TEXT NOT NULL,
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds')),
 CHECK(length(trim(client_id))>0 AND length(trim(operation))>0 AND length(trim(request_hash))>0 AND length(trim(resource_type))>0),
 UNIQUE(client_id,operation,operation_key)
);
CREATE TABLE lifecycle_events(
 id INTEGER PRIMARY KEY,entity_type TEXT NOT NULL,entity_id INTEGER NOT NULL,event_type TEXT NOT NULL,actor TEXT NOT NULL CHECK(length(trim(actor))>0),
 correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),metadata_schema_version INTEGER NOT NULL CHECK(metadata_schema_version>=1),metadata_json TEXT,created_at TEXT NOT NULL,
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at) IS NOT NULL AND created_at=strftime('%Y-%m-%dT%H:%M:%SZ',created_at,'+0 seconds'))
);
