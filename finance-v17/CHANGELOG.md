# Finance V17

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
