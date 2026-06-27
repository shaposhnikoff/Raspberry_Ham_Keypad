# radio_key_daemon Role

Deploys Radio Key Daemon to Raspberry Pi OS or another Debian-family target.

## Defaults

Important defaults are defined in `defaults/main.yml`:

- `radio_key_daemon_repo_url`: Git repository to deploy.
- `radio_key_daemon_version`: Branch, tag, or commit to checkout.
- `radio_key_daemon_install_dir`: Remote checkout path.
- `radio_key_daemon_config_src`: Local config copied to the target when missing.
- `radio_key_daemon_overwrite_config`: Whether to overwrite an existing config.
- `radio_key_daemon_web_host` and `radio_key_daemon_web_port`: Web bind address.
- `radio_key_daemon_allow_command_run`: Enables per-key web run buttons.
- `radio_key_daemon_manage_user`: Creates the service user, `pi` by default.
- `radio_key_daemon_install_rigctld_service`: Installs `rigctld`, enabled by default.
- `radio_key_daemon_rigctld_*`: `rigctld` service settings.

## Example

```yaml
---
- name: Deploy Radio Key Daemon
  hosts: raspberry_pi
  become: true
  gather_facts: true

  roles:
    - role: radio_key_daemon
```

## Check Mode

The role is check-mode friendly. On a clean host, tasks that require files
created by a real checkout are skipped with an explanatory message instead of
failing dry-run validation.

## Tags

- `packages`
- `app`
- `config`
- `helpers`
- `systemd`
- `rigctld`
- `validate`
