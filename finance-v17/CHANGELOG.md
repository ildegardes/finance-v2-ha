# Finance V17

## 0.1.25-open-finance.1

- Add allowlisted Open Finance failure diagnostics for account/Item scope and application/resource authentication, correlated with local runs.
- Preserve original error codes, API responses, validation guards, provider calls, bank selection, staging and idempotency. No new migration or financial behavior.
- Never log banking identifiers, credentials, payloads or financial values. Existing configuration and auto-sync preferences are unchanged.
- Release evidence distinguishes synthetic ARM64/container checks from Supervisor homologation. See docs/open-finance/RELEASE_0.1.25.md for deployment and schema-10 rollback gates.

## 0.1.24-open-finance.1

- Replace the unsupported-auto-sync startup rejection with isolated cached-coverage workers. Enable the default only for new options; preserve explicit persisted false and document activation after update.
- Reuse manual coverage ingestion, per-connection leases, binding verification and revision history; record automatic runs as `AUTO:coverage` rather than impersonating the owner.
- Isolate incomplete institution credentials with fixed diagnostics, without preventing API startup or a valid peer connection.
- Serve HTTP requests concurrently with a limit of 16 workers. Keep the wrapper, financial scheduler, migrations, OAuth/MCP permissions and protected Unicode bytes unchanged.
- Incorporate H06-R cancellation: bounded ingestion shutdown, INTERRUPTED audit state, fenced lease recovery and discarded late I/O results; at most one unresolved transport call per institution.
- Avoid duplicate startup collections after a recent automatic success and back off after recent failure. Do not turn expired authorization into empty product snapshots; expose Item/consent diagnostics.
- No new migration, Item update, live balance, consent renewal, official financial promotion or automatic modification of existing options. Tests and residual Supervisor limitations are documented separately.

## 0.1.23-open-finance.1 — experimental review candidate

- Add versioned cached-read contracts for configured Items, resource permissions, consents, bank/credit accounts, balances, limits, transactions, investment positions/movements, loans, bills and statement references.
- Add migration 010 with extended staging, composite identities, parent/run foreign keys, revision history and collection quality. Preserve migrations 001–009 and all official financial tables.
- Reuse existing leases/fencing and save legacy/extended projections atomically per page. Manual full scans are idempotent; missing records are NOT_SEEN, never silently deleted.
- Add owner-only resource/history/progress queries and an explicitly confirmed manual cache-collection action. No remote Item update, live balance, SCR, consent modification, payment or automatic synchronization.
- Extend Open Finance to six responsive areas, with global privacy for monetary values and sensitive numerical fields. Do not infer balances, returns or consolidated wealth.
- Keep the eight historical protected artifacts, lifecycle, financial core, scheduler and OAuth/MCP permissions unchanged. MCP reports the candidate version.
- This candidate is published only for review on its work branch. No stable promotion, Supervisor homologation or Home Assistant update is implied.

## 0.1.22-open-finance.1 — local release preparation

- Add global monetary privacy with a header eye button, hidden-by-default presentation and a persistent local browser preference.
- Organize Open Finance into Overview, Flow, Assets and Connections; preserve existing query filters and pagination without inventing balances or investment positions.
- Improve Brazilian date/amount presentation, friendly account labels, keyboard navigation and responsive layouts.
- Preserve schema 9, migrations 001–009, HTTP contracts, authentication, financial rules, lifecycle and scheduler. No automatic bank sync or financial promotion.
- Privacy is presentation only: API responses, form values and browser memory are not encrypted or removed.
- Known pre-existing limitation: recurring revenue editing can also open a materialization dialog through the legacy delegated handler. Phase A did not fix or certify financial execution of that flow.
- This is a local, unpublished release preparation; publication, installation and Home Assistant operations require separate authorization.

## 0.1.21-open-finance.1 — local composition, not published

- Reuse the existing manual Pluggy staging, owner-only HTTP contracts and Open Finance query interface.
- Include additive migration 009 and the fixed Unicode13 search profile with its notices.
- Preserve the published 0.1.20-lifecycle.1 lifecycle functions and monitoring; add only private Pluggy options loading.
- Preserve financial rules, OAuth/MCP, existing options and the financial scheduler; no automatic bank sync or promotion.
- Local synthetic review candidate only. No production update, real banking access or installation is authorized.

## 0.1.18

- Add inclusive start/end expense_date competence bounds to finance_list_expenses, reusing the canonical expense API with existing search, pagination and lifecycle behavior.
- Add explicit Dashboard month selection to finance_get_summary; omitted month keeps the configured Finance clock/timezone's current month.
- Clarify tool schemas and descriptions: competence differs from due dates, invoice obligations and realized cash flow. Preserve the HTTP current_month due-date preset and schema 8 without migrations.

## 0.1.17

- Guarantee eligible recurring expense occurrences immediately after canonical HTTP/UI/MCP creation, using the shared domain materializer and scheduler year-end horizon.
- Commit new series, occurrences, invoice effects and permanent creation identity atomically; preserve replay and unique logical slots under concurrent scheduler/manual catch-up.
- Default the recurring expense UI materialization dialog to year end instead of today; explicit earlier limits remain supported and may legitimately create zero occurrences.
- Preserve OAuth refresh, seven recurring MCP tools, protected history, schema 8 and all existing migrations. Real-host scheduler/log status is not inferred from local fixtures.

## 0.1.16

- Add explicit MCP recurring-expense list/get/create, prospective change, this-and-future, individual planned-payment override and terminal end tools using canonical API/domain operations.
- Create one rule, not manual monthly expenses; keep materialization in the domain/scheduler and preserve paid/protected history, six methods and month-end calendar rules.
- Reuse permanent transactional identities for creation and all exposed writes; bind category in the new prospective external identity scope without changing legacy UI replay keys.
- Preserve OAuth authorization/refresh rotation, bearer capabilities and schema 8. BANK_TRANSFER recurrence support remains deferred; no migration or deployment is implied.

## 0.1.15

- Add durable public-client OAuth refresh tokens with schema migration 008.
- Keep access tokens short-lived (15 minutes); rotate single-use refresh tokens within a 30-day absolute authorization family lifetime.
- Store only token hashes; atomically rotate tokens and revoke a family on proven reuse, including its access tokens.
- Preserve client/resource binding, non-escalating scopes, legacy access tokens, PKCE, exact callbacks, consent, CSRF and browser CSP.
- Advertise the refresh_token grant and explain automatic renewal in the consent page. No deployment or real-client validation is implied by this local release.

## 0.1.14

- Add a clear planned-payment scope selector for recurring expenses: only this entry or this and eligible future entries, using the existing protected-history contracts.
- Keep prospective series edits separate, require the card when applicable, and normalize unused payment associations without recording payments.
- Keep the recurring-origin indicator inline with the entry name, with accessible expense/revenue tooltips.
- Preserve schema 7, scheduler, realized-flow semantics, and OAuth security; no new migration.

## 0.1.13

- Materialize recurring expenses on every scheduler cycle, preserving annual catch-up, slot identity, retries, and protected history.
- Use net payment/receipt flows by event date in the realized six-month chart, including reversals and invoice payments without double counting.
- Show current competence entries with a discreet recurring-origin indicator and links to the existing expense and revenue lists.
- Allow the six existing planned payment methods for only one recurring occurrence or this and future occurrences; preserve protected and paid history.
- Preserve prospective recurrence slot ordinals before materialization; no schema change or new migration.

## 0.1.12

- Allow the exact validated OAuth callback in the consent document's CSP so Chromium can follow the authorization redirect.
- Preserve the strict login CSP, other security directives, redirect validation, PKCE, CSRF, browser binding, and single-use authorization codes.

## 0.1.11

- Add an isolated MCP Inspector OAuth client with an exact loopback callback.

## 0.1.10

- Accept OAuth authorization POST requests from opaque browser origins (`Origin: null`) while preserving CSRF, binding, and exact-origin protections.

## 0.1.9

- Improve OAuth/MCP compatibility with legitimate optional request parameters, including ChatGPT's `ui_locales`.
- Preserve strict redirect, PKCE, scope, resource, CSRF, consent, and authorization-code validation.

## 0.1.8

- Automatically upgrade existing Finance V2 databases before startup.
- Apply the schema 6 to 7 upgrade safely before API and scheduler startup.
- Add release and migration consistency checks.
- Preserve the OAuth and MCP support introduced in 0.1.7.
