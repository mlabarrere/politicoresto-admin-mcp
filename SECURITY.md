# Security Policy

## Supported versions

Only the latest `0.x` release receives security fixes.

| Version | Supported |
| ------- | --------- |
| 0.x     | ✅        |

## Reporting a vulnerability

**Please do not open a public issue for security reports.**

Email `SECURITY_CONTACT` with:
- A description of the issue and its impact.
- Steps to reproduce (PoC welcome but not required).
- Whether the bug is already public, and any coordinated-disclosure timeline you need.

You should receive an acknowledgement within 5 business days. We aim to ship a
fix (or a mitigation plan with a timeline) within 30 days of confirmation.
Credit is given in the release notes unless you prefer to stay anonymous.

## Threat model (what this project does and does not protect)

`politicoresto-admin-mcp` is a **local, single-user admin tool**:

- It runs over the stdio transport, launched by Claude Desktop on the user's
  machine.
- It authenticates with Supabase via a `service_role` key that **bypasses
  Row-Level Security** on every request. Anyone who can make this process
  send PostgREST requests has full read/write access to the target project.
- It is **not** designed to be exposed over HTTP or to multiple users. Doing
  so effectively publishes the service_role key to anyone who can reach the
  endpoint.

Because of this, the most common classes of vulnerability to watch for are:

- **Service-role key leakage** — through logs, screenshots, committed files,
  CI artifacts, or unexpected error messages.
- **Command/env injection** — anything that lets an attacker influence which
  URL or key the process starts with (e.g. via a malicious `.env` file shipped
  in a repository the user opens).
- **Prompt-injected write operations** — a malicious document or tool output
  tricking Claude into issuing writes. Mitigated in the MCP contract by the
  explicit `set_acting_user` handshake that a human confirms before any write.

## If a service-role key has leaked

1. **Rotate immediately.** Open the Supabase dashboard for the affected
   project (`nvwpvckjsvicsyzpzjfi` for staging, `gzdpisxkavpyfmhsktcg` for
   production). Go to *Settings → API → Service Role Secret* and click
   *Regenerate*. The old key becomes invalid the moment the new one is
   generated.
2. **Scrub the leak surface.** If the key was committed, rotating is not
   enough — the bad commit is still in the repo history. Consider
   `git filter-repo` or `git filter-branch` to rewrite history and force-push
   (coordinate with any collaborators first).
3. **Audit for abuse.** Check `auth.audit_log_entries` and any service logs
   covering the exposure window. Inspect recent writes to sensitive tables
   (`app_profile`, `profile_vote_history`, etc.).
4. **Update every consumer.** Update your local `.env`, the Claude Desktop
   config, and any CI/CD secret store that uses the key.
