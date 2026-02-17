# Flock You – Pi Zero setup (Ansible)

This directory configures a Raspberry Pi Zero 2 W (Raspberry Pi OS Lite) with GPS (UART + PPS), the Flock You API, Caddy, watchdog, and the button/AP daemon.

## Prerequisites

- Raspberry Pi Zero 2 W with Raspberry Pi OS Lite
- SSH and Wi‑Fi (or Ethernet) configured; you can log in as a user with sudo
- Ansible on your machine (`pip install ansible` or use your distro package)

## Quick run

1. Edit **`inventory.yml`**: set `ansible_host` to your Pi’s IP or hostname (e.g. `flock-pi.local`) and `ansible_user` to your Pi username.
2. From the repo root or from `setup`:
   ```bash
   cd setup
   ansible-playbook -i inventory.yml playbook.yml
   ```
   Or use the helper script:
   ```bash
   cd setup
   chmod +x run.sh
   ./run.sh
   ```
   To target a single host: `./run.sh flock_pi`.

The playbook will:

1. Configure serial and PPS (config.txt, cmdline.txt), install gpsd/chrony, then **reboot** the Pi.
2. Wait for the Pi to come back.
3. Clone the repo, create venv, deploy the API (systemd), Caddy (HTTPS with self-signed cert), watchdog (health check + restart API), and the button/AP daemon (short press = toggle AP, long press = shutdown).

After running, open the Pi in a browser via `https://<ansible_host>` (accept the self-signed certificate). The API is served behind Caddy; use `/api/health` for GPS/PPS status.
