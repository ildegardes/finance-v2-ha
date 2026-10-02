-- V17: authorized multimethod installments; preserve V16 card rows and identities.
CREATE TABLE installment_series_v17(
 id INTEGER PRIMARY KEY,purchase_date TEXT NOT NULL,card_id INTEGER REFERENCES cards(id),
 payment_method TEXT NOT NULL DEFAULT 'CREDIT_CARD' CHECK(payment_method IN('CREDIT_CARD','AUTO_DEBIT','PIX','BANK_TRANSFER','BANK_SLIP','DEBIT','CASH')),
 account_id INTEGER REFERENCES accounts(id),first_due_date TEXT,
 original_total_cents INTEGER NOT NULL CHECK(original_total_cents>0),
 installment_count INTEGER NOT NULL CHECK(installment_count>0),ended_from_installment INTEGER,ended_at TEXT,
 CHECK((payment_method='CREDIT_CARD' AND card_id IS NOT NULL AND account_id IS NULL AND first_due_date IS NULL) OR (payment_method IN('AUTO_DEBIT','PIX','BANK_TRANSFER','DEBIT') AND card_id IS NULL AND account_id IS NOT NULL AND first_due_date IS NOT NULL) OR (payment_method='CASH' AND card_id IS NULL AND account_id IS NULL AND first_due_date IS NOT NULL) OR (payment_method='BANK_SLIP' AND card_id IS NULL AND first_due_date IS NOT NULL)),
 CHECK(first_due_date IS NULL OR (date(first_due_date,'+0 days') IS NOT NULL AND first_due_date=date(first_due_date,'+0 days'))),
 CHECK(date(purchase_date,'+0 days') IS NOT NULL AND purchase_date=date(purchase_date,'+0 days')),
 CHECK(ended_from_installment IS NULL OR ended_from_installment BETWEEN 1 AND installment_count),
 CHECK(ended_at IS NULL OR (strftime('%Y-%m-%dT%H:%M:%SZ',ended_at) IS NOT NULL AND ended_at=strftime('%Y-%m-%dT%H:%M:%SZ',ended_at,'+0 seconds')))
);
INSERT INTO installment_series_v17(id,purchase_date,card_id,original_total_cents,installment_count,ended_from_installment,ended_at) SELECT id,purchase_date,card_id,original_total_cents,installment_count,ended_from_installment,ended_at FROM installment_series;
CREATE TABLE expenses_v17(
 id INTEGER PRIMARY KEY,description TEXT NOT NULL CHECK(length(trim(description))>0),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),expense_date TEXT NOT NULL,due_date TEXT,
 planned_payment_method TEXT NOT NULL CHECK(planned_payment_method IN('PIX','BANK_TRANSFER','DEBIT','CASH','BANK_SLIP','AUTO_DEBIT','CREDIT_CARD')),
 category_id INTEGER NOT NULL REFERENCES categories(id),account_id INTEGER REFERENCES accounts(id),card_id INTEGER REFERENCES cards(id),
 invoice_id INTEGER REFERENCES invoices(id),recurring_series_id INTEGER REFERENCES recurring_series(id),
 recurring_version_id INTEGER REFERENCES recurring_series_versions(id),recurrence_occurrence_key TEXT,logical_slot_lineage_key TEXT,
 materialization_slot_key TEXT,installment_series_id INTEGER REFERENCES installment_series(id),installment_number INTEGER,
 lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN('ACTIVE','CANCELLED','SUPERSEDED')),
 superseded_at TEXT,superseded_by_expense_id INTEGER REFERENCES expenses(id),supersession_reason_code TEXT CHECK(supersession_reason_code IS NULL OR length(trim(supersession_reason_code))>0),supersession_correlation_id TEXT CHECK(supersession_correlation_id IS NULL OR length(trim(supersession_correlation_id))>0),
 notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 CHECK(date(expense_date,'+0 days') IS NOT NULL AND expense_date=date(expense_date,'+0 days')),CHECK(due_date IS NULL OR (date(due_date,'+0 days') IS NOT NULL AND due_date=date(due_date,'+0 days'))),
 CHECK((planned_payment_method='CREDIT_CARD' AND card_id IS NOT NULL AND invoice_id IS NOT NULL AND account_id IS NULL AND due_date IS NULL) OR
       (planned_payment_method IN('PIX','BANK_TRANSFER','DEBIT','AUTO_DEBIT') AND card_id IS NULL AND invoice_id IS NULL AND account_id IS NOT NULL) OR
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
INSERT INTO expenses_v17 SELECT * FROM expenses;
DROP TABLE expenses;
DROP TABLE installment_series;
ALTER TABLE installment_series_v17 RENAME TO installment_series;
ALTER TABLE expenses_v17 RENAME TO expenses;
CREATE UNIQUE INDEX ux_installment ON expenses(installment_series_id,installment_number) WHERE installment_series_id IS NOT NULL;
