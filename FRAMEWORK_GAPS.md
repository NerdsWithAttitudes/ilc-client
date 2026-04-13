# Framework Gaps

This note tracks helper code in `ilc-client-public` that could later move into
TinyChain itself. The current package behavior is correct; these are
consolidation opportunities.

1. Auth-context propagation for library calls
- Current local shim: `AuthContext` and `AuthContext.from_env(...)`.
- Desired framework behavior: standardized propagation of token, host, key, and
  optional validity window across library calls.

2. Authenticated JSON route helper
- Current local shim: `post_json(...)` in `src/ilc/library.py`.
- Desired framework behavior: typed authenticated POST helper with envelope
  normalization.

3. Key-format conversion helper
- Current local shim: `public_key_hex_from_b64(...)`.
- Desired framework behavior: canonical key-format conversion utility.

4. Token validity-window parsing helper
- Current local shim: `token_validity_window(...)`.
- Desired framework behavior: canonical token claim window parser in client API.
