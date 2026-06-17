# Fragalysis Stack (Ansible)

An Ansible project that deploys the **Fragalysis Stack** (a Django web app, Celery workers, PostgreSQL,
Redis, pgBouncer and supporting services) onto a Kubernetes cluster. It is designed to run
from AWX/Ansible Tower (which injects `tower_*` and credential variables) but can also run from a
control machine. The host is `localhost` with a local connection — all work happens against a remote
cluster via the `k8s`/`k8s_info` modules, not against the Ansible host itself.

## Running the playbooks

There is one role, `fragalysis_stack`, with four entrypoint playbooks that differ only in which
`tasks_from` they load:

```bash
# Deploy / update the full stack (tasks/main.yaml)
ansible-playbook site-fragalysis-stack.yaml

# Fast in-place app update only — stack, worker, beat (tasks/update.yaml)
ansible-playbook site-fragalysis-stack_update.yaml

# Remove stack + django secret, keep DB and (by default) media volume (tasks/shutdown.yaml)
ansible-playbook site-fragalysis-stack_shutdown.yaml

# Remove stack, redis, DB and all volumes but keep namespace + cert (tasks/wipe.yaml)
ansible-playbook site-fragalysis-stack_wipe.yaml
```

`stack_image_tag` must always be provided (no default that works) — pass it with `-e stack_image_tag=...`
or via an AWX survey. `ansible.cfg` sets the inventory to `inventory.yaml`.

### Secrets

Sensitive values must be supplied at run time — via `-e`, an extra-vars file, or AWX
credentials/surveys. The relevant `defaults/main.yaml` entries are blank placeholders documenting
what is required: the rsync/rclone backup credentials, the xchem ISPyB secrets, the Squonk2/Keycloak
secrets, and the TA-auth service config.

## Authentication model

`tasks/prep.yaml` reads the path to the kubeconfig from the `KUBECONFIG` environment variable into the
`k8s_kubeconfig` fact, and the playbooks assert it is set. All cluster access authenticates through it.

`tasks/main.yaml` applies the kubeconfig via `module_defaults: group/k8s` so every downstream `k8s` task
inherits it. When adding cluster operations, rely on this `module_defaults` mechanism rather than passing
`kubeconfig` per-task (the `update.yaml` play is the exception — it passes it explicitly because it does
not go through `main.yaml`).

## Developer vs non-developer (production) deployments

Controlled by `stack_is_for_developer` (default `yes`). This is the single most important branch in the
project and governs namespace/URL generation in `prep.yaml` and `deploy-stack.yaml`:

- **Developer**: must run from AWX. `stack_namespace` must be blank — it is generated as
  `stack-{{ tower_user_name }}-{{ stack_name }}`, and the URL as
  `fragalysis-{{ tower_user_name }}-{{ stack_name }}.{{ stack_hostname }}`. `prep.yaml` enforces that a
  `User (<name>)` job template can only be run by that named user, and that `stack_name` is lower-case letters.
- **Non-developer**: `stack_namespace` must be set explicitly and must be one of a hard-coded allow-list
  (`staging-stack`, `production-stack`, `v2-production-stack`, `dummy-production-stack`). The URL is
  `stack_hostname` verbatim. Several DEBUG-only features are disabled in `production` deployment mode.

## Deploy flow and idempotency conventions

`tasks/deploy.yaml` orchestrates: namespace + serviceaccount → backup secrets → database (unless
`database_host` points at an external DB) → redis + stack (unless `stack_skip_deploy`). Everything except
the graph lives in the one `stack_namespace`; undeploy simply deletes the namespace (`undeploy.yaml`).

Key patterns to preserve when editing tasks:

- **Secrets/passwords are written once.** Tasks `k8s_info` the existing Secret first; if it exists, values
  are read back (base64-decoded) into `*_fact` variables and the Secret is *not* rewritten. Auto-generated
  passwords use the `lookup('password', ...)` pattern with deliberately differing lengths to dodge an
  Ansible caching collision (see comments in `vars/main.yaml`). Never make these tasks unconditionally
  overwrite a Secret — it would rotate live DB/django credentials.
- **PVCs**: create the claim, then optionally wait for `status.phase == 'Bound'` gated on `wait_for_bind`
  (off by default because multi-zone PVCs only bind once a consumer Pod exists).
- **Readiness waits**: Pods are polled via `k8s_info` with `until:` on `containerStatuses[0].ready`,
  `retries` derived as `wait_timeout / delay`. The stack is a StatefulSet scaled to `stack_replicas`,
  initialised `stack-0`..`stack-(N-1)`; `wait-for-stack.yaml` is looped per replica and can first wait for
  un-ready (`stack_wait_for_termination`) before waiting for ready.
- **Pre-existing volume guards**: `stack_allow_pre_existing_database_volume` /
  `..._media_volume` exist to force a `shutdown` between production→staging replications. Don't relax them.

## Variables

- `defaults/main.yaml` — user-facing knobs (image tags, replicas, hostnames, backups, Keycloak/OIDC,
  Squonk2, email, feature flags). Heavily commented; read it before adding a new variable.
- `vars/main.yaml` — internal tuning the user is not expected to change (resource limits, image registries,
  timeouts, generated passwords, `stack_state`).

Templates in `roles/fragalysis_stack/templates/*.j2` are the Kubernetes manifests rendered via
`lookup('template', ...)`. Adding a new K8s object means adding a template and a `k8s:` task referencing it.
