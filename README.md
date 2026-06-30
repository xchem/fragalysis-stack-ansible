# Fragalysis Ansible

[![Latest release][release-badge]][releases]

A project of Ansible playbooks. Playbooks that deploy the components
that a part fo the **Fragalysis** suite into Kubernetes. The suite
includesthe **Fragalysis Stack** (a Django web app, Celery workers,
PostgreSQL, Redis, pgBouncer and supporting services),
and the **Target Access Authenticator**. Playbooks are designed to run
from a control machine. The host is `localhost` with a local connection —
all work happens against a remote cluster via the
`k8s`/`k8s_info` modules, not against the Ansible host itself.

Each component exists as an Ansible **Role** with a corresponding
`site-<Role>.yaml` play. Roles use `vars/sensitive.vault` to store
sensitive (non-public) material required for the installation.
When a play uses `tasks_from` the site filename will include the name
of the task file. For example when the Fragalysis Stack play runs
`wipe.yaml` its site file is called `site-fragalysis-stack_wipe.yaml`.

## Prerequisites

You are expected to have a suitable Python (the project targets Python
3.12) and the [uv][uv] package manager installed. `uv` creates the
virtual environment and runs the playbooks (e.g.
`uv run ansible-playbook ...`).

You also need access to the Kubernetes cluster, where a **Namespace**
is expected to exist for each component. For example, when there are
multipole stacks (production and legacy) each stack is expected to
reside in its own **Namespace**.

## Variables

- `defaults/main.yaml` — user-facing knobs (image tags, replicas,
  hostnames, backups, Keycloak/OIDC, Squonk2, email, feature flags).
  Heavily commented; read it before adding a new variable.
- `vars/main.yaml` — internal tuning the user is not expected to change
  (resource limits, image registries, timeouts, generated passwords,
  `stack_state`).

A `parameters-template.yaml` file exposes some of the more useful _tunable_
variables. You are encouraged to inspect all the variables but also copy
`parameters-template.yaml` to `parameters.yaml` in order to fine-tune the
installation to suit your needs.

## Running the playbooks

There is one role, `fragalysis_stack`, with four entrypoint playbooks
that differ only in which `tasks_from` they load:

```bash
# Deploy / update the full stack (tasks/main.yaml)
uv run ansible-playbook site.yaml

# Fast in-place app update only — stack, worker, beat (tasks/update.yaml)
uv run ansible-playbook site_update.yaml

# Remove stack + django secret, keep DB and (by default) media volume
# (tasks/shutdown.yaml)
uv run ansible-playbook site_shutdown.yaml

# Remove stack, redis, DB and all volumes but keep namespace + cert
# (tasks/wipe.yaml)
uv run ansible-playbook site_wipe.yaml
```

`stack_image_tag` must always be provided (no default that works) — pass
it with `-e stack_image_tag=...` or via an AWX survey. `ansible.cfg` sets
the inventory to `inventory.yaml`.

### Secrets

Sensitive values must be supplied at run time — via `-e`, an extra-vars
file, or AWX credentials/surveys. The relevant `defaults/main.yaml`
entries are blank placeholders documenting what is required: the
rsync/rclone backup credentials, the xchem ISPyB secrets, the
Squonk2/Keycloak secrets, and the TA-auth service config.

## Authentication model

`tasks/prep.yaml` reads the path to the kubeconfig from the `KUBECONFIG`
environment variable into the `k8s_kubeconfig` fact, and the playbooks
assert it is set. All cluster access authenticates through it.

`tasks/main.yaml` applies the kubeconfig via `module_defaults: group/k8s`
so every downstream `k8s` task inherits it. When adding cluster
operations, rely on this `module_defaults` mechanism rather than passing
`kubeconfig` per-task (the `update.yaml` play is the exception — it
passes it explicitly because it does not go through `main.yaml`).

## Deploy flow and idempotency conventions

`tasks/deploy.yaml` orchestrates: namespace + serviceaccount → backup
secrets → database (unless `database_host` points at an external DB) →
redis + stack (unless `stack_skip_deploy`). Everything except the graph
lives in the one `stack_namespace`; undeploy simply deletes the namespace
(`undeploy.yaml`).

Key patterns to preserve when editing tasks:

- **Secrets/passwords are written once.** Tasks `k8s_info` the existing
  Secret first; if it exists, values are read back (base64-decoded) into
  `*_fact` variables and the Secret is *not* rewritten. Auto-generated
  passwords use the `lookup('password', ...)` pattern with deliberately
  differing lengths to dodge an Ansible caching collision (see comments
  in `vars/main.yaml`). Never make these tasks unconditionally overwrite
  a Secret — it would rotate live DB/django credentials.
- **PVCs**: create the claim, then optionally wait for
  `status.phase == 'Bound'` gated on `wait_for_bind` (off by default
  because multi-zone PVCs only bind once a consumer Pod exists).
- **Readiness waits**: Pods are polled via `k8s_info` with `until:` on
  `containerStatuses[0].ready`, `retries` derived as
  `wait_timeout / delay`. The stack is a StatefulSet scaled to
  `stack_replicas`, initialised `stack-0`..`stack-(N-1)`;
  `wait-for-stack.yaml` is looped per replica and can first wait for
  un-ready (`stack_wait_for_termination`) before waiting for ready.
- **Pre-existing volume guards**: `stack_allow_pre_existing_database_volume`
  / `..._media_volume` exist to force a `shutdown` between
  production→staging replications. Don't relax them.

## Templates

Templates in `roles/fragalysis_stack/templates/*.j2` are the Kubernetes
manifests rendered via `lookup('template', ...)`. Adding a new K8s object
means adding a template and a `k8s:` task referencing it.

## License

Licensed under the [Apache License, Version 2.0][apache-2.0]; the full
text is in the [LICENSE][license] file.

[apache-2.0]: https://www.apache.org/licenses/LICENSE-2.0
[license]: LICENSE
[release-badge]: https://img.shields.io/github/v/release/xchem/fragalysis-stack-ansible?sort=semver
[releases]: https://github.com/xchem/fragalysis-stack-ansible/releases/latest
[uv]: https://docs.astral.sh/uv/
