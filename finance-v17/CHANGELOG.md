# Finance V17

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
