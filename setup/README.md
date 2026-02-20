# Flock You – Pi Zero setup (Ansible)

This directory configures a Raspberry Pi Zero 2 W (Raspberry Pi OS Lite) with GPS (UART + PPS), the Flock You API, Caddy, watchdog, and the button/AP daemon.

## Prerequisites

- **Pi**: Raspberry Pi Zero 2 W with Raspberry Pi OS Lite; SSH and Wi‑Fi (or Ethernet) configured; you can log in as a user with `sudo`.
- **Control machine**: Ansible 2.9+ (`pip install ansible` or your distro package). SSH access from your machine to the Pi (key-based or password; use `-k` with `ansible-playbook` if you use password auth).

## One-place config

The only required edit is **`inventory.yml`**:

- `ansible_host`: your Pi’s IP or hostname (e.g. `192.168.1.100` or `flock-pi.local`).
- `ansible_user`: your Pi username (e.g. `pi`).

Optional: override variables in **`group_vars/all.yml`** or via `-e` (e.g. `ap_passphrase`, `secret_key`, `repo_url`, `timezone`). Defaults are fine for a first run.

## Quick run

1. Edit **`inventory.yml`** as above.
2. From the **`setup`** directory run the playbook:

   ```bash
   cd setup
   ansible-playbook -i inventory.yml playbook.yml
   ```

   To skip the final reboot:  
   `ansible-playbook -i inventory.yml playbook.yml -e reboot_after_setup=false`

The playbook will:

1. Configure serial and PPS (config.txt, cmdline.txt), install gpsd/chrony, then **reboot** the Pi.
2. Wait for the Pi to come back.
3. Clone the repo, create venv, deploy the API (systemd), Caddy (HTTPS with self-signed cert), watchdog (health check + restart API), and the button/AP daemon (short press = toggle AP, long press = shutdown). Optionally **reboot** again at the end (disable with `-e reboot_after_setup=false`).

After running, open the Pi in a browser via **`https://<ansible_host>`** (accept the self-signed certificate). The API is served behind Caddy; use `/api/health` for GPS/PPS status.

## Button wiring (toggle AP / long-press shutdown)

The button/AP daemon uses **BCM GPIO 17** with internal pull-up. Wire a momentary push-button between:

- **GPIO 17** → **Physical pin 11** (40-pin header)
- **GND** → e.g. **Physical pin 6, 9, or 14**

Short press toggles the WiFi AP (and shared-scan mode); long press (~3 s) triggers a clean shutdown. Change `button_gpio` or `long_press_seconds` in `group_vars/all.yml` if needed.

## If the Pi is unreachable after the first reboot

- **Check the IP**: After a reboot, DHCP may assign a different address. Try the hostname (e.g. `ssh pi@flock-pi.local` or `ssh pi@flock_pi.local`) or look up the Pi’s lease in your router / access point.
- **Boot backups**: Before editing boot config, the playbook copies `config.txt` and `cmdline.txt` to `*.pre-uart-pps` in the same directory. If the Pi no longer boots, mount the SD card on another machine and restore:
  - `cp /boot/firmware/cmdline.txt.pre-uart-pps /boot/firmware/cmdline.txt` (Bookworm) or `/boot/` on older OS.
  - Do the same for `config.txt` if needed, then re-run the playbook after fixing.
