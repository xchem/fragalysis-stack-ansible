#!/usr/bin/env python3
"""An Ansible Vault password *client* script.

Ansible treats a vault password file as a "client" script when the file
is executable and its name (without extension) ends with '-client'.
For such scripts Ansible appends '--vault-id <label>' to the call and
reads the password from stdout. See Ansible's parsing/vault module
(script_is_client / ClientScriptVaultSecret) for the contract.

The <label> is the vault-id label, which here is the installation name
(e.g. 'argus' from '--vault-id argus@vault-client.py'). The password for
that installation is read from the environment variable

    ANSIBLE_VAULT_PASSWORD_<INSTALLATION>

where <INSTALLATION> is the label upper-cased with every character that
is not a letter or digit replaced by an underscore. For example the
'argus' installation's password comes from ANSIBLE_VAULT_PASSWORD_ARGUS.

Keeping the password in the environment (rather than on disk or the
command line) means it can be supplied from a GitHub Actions secret in CI
without being written to a file or echoed into the logs.

Exit codes follow Ansible's expectations:
  0  the password was found and printed to stdout
  2  no password is available for the requested vault-id (VAULT_ID_UNKNOWN)
  1  the script was called incorrectly
"""

import argparse
import os
import re
import sys

# Ansible interprets this return code as "this client has no secret for
# the requested vault-id" rather than a hard error, so it can move on to
# any other configured vault secrets.
VAULT_ID_UNKNOWN_RC = 2

# Prefix for the per-installation password environment variables.
ENV_PREFIX = "ANSIBLE_VAULT_PASSWORD"


def env_var_name(vault_id_label):
    """Return the environment variable holding a vault-id's password.

    A blank/None label maps to the bare ENV_PREFIX so the script can also
    be used as a plain (non-client) vault password file.
    """
    if not vault_id_label:
        return ENV_PREFIX
    sanitised = re.sub(r"[^A-Za-z0-9]", "_", vault_id_label).upper()
    return f"{ENV_PREFIX}_{sanitised}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Ansible passes the vault-id label here; it is absent when the script
    # is used as an ordinary --vault-password-file.
    parser.add_argument("--vault-id", dest="vault_id", default=None)
    args = parser.parse_args()

    variable = env_var_name(args.vault_id)
    password = os.environ.get(variable)

    if not password:
        # Never let this pass silently - report (to stderr, not stdout)
        # which variable was expected so the misconfiguration is obvious,
        # without revealing any secret value.
        sys.stderr.write(
            f"No vault password for vault-id "
            f"'{args.vault_id or '(none)'}': set the environment "
            f"variable '{variable}'.\n"
        )
        sys.exit(VAULT_ID_UNKNOWN_RC)

    # The password is the script's sole stdout output, as Ansible expects.
    sys.stdout.write(password)


if __name__ == "__main__":
    main()
