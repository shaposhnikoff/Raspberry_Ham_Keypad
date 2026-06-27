# Ansible Deployment

This directory contains a thin deploy playbook and the reusable
`radio_key_daemon` role. The role deploys `radio_key_daemon` to a Raspberry Pi
and starts the systemd service in combined keypad plus web mode.

## Inventory

Copy the example inventory and replace the host address:

```bash
cp ansible/inventory.example.yml ansible/inventory.yml
```

Edit `ansible/inventory.yml`:

```yaml
all:
  children:
    raspberry_pi:
      hosts:
        radio-pi:
          ansible_host: 192.168.10.50
          ansible_user: pi
          ansible_python_interpreter: /usr/bin/python3
          # Optional: uncomment in ansible/inventory.yml if needed.
          # ansible_ssh_private_key_file: ~/.ssh/id_raspberry_pi
```

Use a placeholder in committed examples only. Put the real SSH private key path
in your local ignored `ansible/inventory.yml`, or use `~/.ssh/config` / SSH
agent.

## Dry Run

Run a check first:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --check --diff
```

## Deploy

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml
```

By default the role:

- Installs `acl`, `git`, `libhamlib-utils`, `python3`, `python3-evdev`, and `python3-yaml`.
- Checks out this repository to `/home/pi/radio-key-daemon`.
- Stores runtime config at `/home/pi/.config/radio-key-daemon/config.yaml`.
- Migrates an existing `/home/pi/radio-key-daemon/config.yaml` to the runtime config path when the new config is missing.
- Copies `ftdx10/ftdx10_keypad_full_config.yaml` to the runtime config path only if it is missing.
- Preserves tracked local checkout changes with `git stash` before updating the repository.
- Copies `ftdx10_cat.py` and `beacon.sh` to `/home/pi/radio`.
- Installs and starts `radio-key-daemon.service`.
- Installs and starts `rigctld.service`.
- Starts the daemon with `--web --host 0.0.0.0 --port 8765 --allow-command-run`.

The playbook does not overwrite an existing remote runtime config unless you pass:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_overwrite_config=true
```

If you want the playbook to fail instead of stashing tracked local checkout
changes, pass:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_preserve_local_checkout_changes=false
```

## Useful Overrides

Deploy a different config:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_config_src=../config.example.yaml
```

Deploy a different branch or tag:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_version=main
```

Disable the `rigctld` service:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e '{"radio_key_daemon_install_rigctld_service": false}'
```

After deployment, open:

```text
http://RASPBERRY_PI_ADDRESS:8765/
```

## Role Layout

```text
ansible/deploy.yml
ansible/roles/radio_key_daemon/
  defaults/main.yml
  handlers/main.yml
  meta/main.yml
  meta/argument_specs.yml
  molecule/default/
  tasks/main.yml
  templates/
```

Most deployment settings live in
`ansible/roles/radio_key_daemon/defaults/main.yml`.

## Validation

```bash
uv run --with yamllint==1.35.1 yamllint -c ansible/.yamllint ansible
uv run --with ansible-core==2.17.7 ansible-playbook \
  -i ansible/inventory.example.yml ansible/deploy.yml --syntax-check
(cd ansible && uv run --with ansible-lint==24.12.2 \
  --with ansible-core==2.17.7 ansible-lint .)
```

The Molecule scenario is intentionally systemd-light. It verifies role syntax
without requiring a full Raspberry Pi systemd container:

```bash
cd ansible/roles/radio_key_daemon
uv run --with molecule==24.12.0 --with ansible-core==2.17.7 molecule syntax
```
