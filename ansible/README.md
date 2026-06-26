# Ansible Deployment

This playbook deploys `radio_key_daemon` to a Raspberry Pi and starts the
systemd service in combined keypad plus web mode.

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
```

## Dry Run

Run a check first:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --check --diff
```

## Deploy

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml
```

By default the playbook:

- Installs `git`, `hamlib-utils`, `python3`, `python3-evdev`, and `python3-yaml`.
- Checks out this repository to `/home/pi/radio-key-daemon`.
- Copies `ftdx10/ftdx10_keypad_full_config.yaml` to `config.yaml` only if it is missing.
- Copies `ftdx10_cat.py` and `beacon.sh` to `/home/pi/radio`.
- Installs and starts `radio-key-daemon.service`.
- Starts the daemon with `--web --host 0.0.0.0 --port 8765 --allow-command-run`.

The playbook does not overwrite an existing remote `config.yaml` unless you pass:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_overwrite_config=true
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

Install and start the optional `rigctld` service:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml \
  -e radio_key_daemon_install_rigctld_service=true
```

After deployment, open:

```text
http://RASPBERRY_PI_ADDRESS:8765/
```
