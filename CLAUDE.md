## Start with the README

See [README.md](README.md) for the project overview, how to run the four playbooks, the vault, the
authentication model, the developer vs non-developer branch, the deploy flow, and where variables live.
Read it before editing — the points below are what matters most when changing code.

## Don't break these invariants

- **Secrets/passwords are written once.** Tasks `k8s_info` an existing Secret first and, if present, read
  its values back into `*_fact` variables instead of rewriting it. Never make these tasks unconditionally
  overwrite a Secret — it rotates live DB/django credentials. The differing `lookup('password', ...)`
  lengths in `vars/main.yaml` are deliberate (they dodge an Ansible caching collision).
- **Cluster credentials flow through `module_defaults: group/k8s`** in `main.yaml`. Add new `k8s` tasks
  there rather than passing `host`/`api_key` per-task. (`update.yaml` is the documented exception — it
  passes them explicitly because it bypasses `main.yaml`.)
- **Pre-existing volume guards** (`stack_allow_pre_existing_database_volume` / `..._media_volume`) exist to
  force a `shutdown` between production→staging replications. Don't relax them.
- **Readiness/PVC waits** poll via `k8s_info` with `until:` and `retries` derived as `wait_timeout / delay`.
  Match this pattern when adding waits.

## House style

- In YAML, list items (`-`) align with their parent key (not indented under it), and YAML lists are
  preferred over inline `[]`.
- No spaces in filenames.
- Use environment variables for sensitive config; never log passwords/tokens.
