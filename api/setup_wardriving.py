#!/usr/bin/env python3
"""
Setup Wardriving

Starts the Flock You server for in-car wardriving with phone (iPhone/Android) + laptop + ESP32.

Modes:
  --hotspot              Laptop joins phone Personal Hotspot. No ad-hoc WiFi. (Recommended with CarPlay/Android Auto)
  --hotspot --ssid X      Connect to hotspot SSID (use with --password to automate)
  (default)              On Linux: create ad-hoc WiFi (FlockYou-Hub), phone joins. On Windows: same as --hotspot.

Security: You do NOT need to specify WPA2 vs WPA3. Windows scans networks and auto-detects.
Linux (iwctl) auto-negotiates with the AP. Use --no-scan on Windows only if the network is not in range yet.
"""
import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
import xml.sax.saxutils as saxutils

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FLOCKYOU_PY = os.path.join(SCRIPT_DIR, 'flockyou.py')


def enable_sleep_inhibit():
    """Prevent laptop sleep during wardriving session. Returns a cleanup callable or None."""
    if sys.platform == 'win32':
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            print('Sleep inhibit enabled (display and system)')
            return lambda: ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception as e:
            print(f'Sleep inhibit failed: {e}')
            return None
    return None


def run_flock_with_sleep_inhibit():
    """Run flockyou.py with sleep inhibit. On Linux uses systemd-inhibit; on Windows uses SetThreadExecutionState."""
    if sys.platform == 'linux':
        try:
            return subprocess.Popen(
                ['systemd-inhibit', '--what=sleep:idle', '--who=Flock You', '--why=Wardriving session', sys.executable, FLOCKYOU_PY],
                cwd=SCRIPT_DIR,
            )
        except FileNotFoundError:
            pass
    # Fallback: run directly (Windows or Linux without systemd-inhibit)
    return subprocess.Popen([sys.executable, FLOCKYOU_PY], cwd=SCRIPT_DIR)


def get_wifi_interface_linux():
    """Get first wireless interface name on Linux."""
    try:
        result = subprocess.run(
            ['iw', 'dev'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith('phy#'):
                continue
            if 'Interface' in line:
                return line.split()[-1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return 'wlan0'


def connect_hotspot_linux(ssid: str, password: str, interface: str | None = None) -> bool:
    """Connect to WiFi hotspot using iwctl (Arch/iwd). Returns True on success."""
    iface = interface or get_wifi_interface_linux()
    try:
        result = subprocess.run(
            ['iwctl', f'--passphrase={password}', 'station', iface, 'connect', ssid],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f'Connected to "{ssid}" on {iface}')
            return True
        print(f'iwctl connect failed: {result.stderr or result.stdout}')
        return False
    except FileNotFoundError:
        print('iwctl not found. Install iwd (Arch: pacman -S iwd).')
        return False
    except subprocess.TimeoutExpired:
        print('Connection timed out.')
        return False


def scan_network_security_windows(ssid: str) -> tuple[str, str] | None:
    """Scan for SSID and return (authentication, encryption) or None if not found/parse failed.
    e.g. ('WPA2-Personal', 'CCMP') or ('WPA3-Personal', 'CCMP')
    """
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'networks'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        auth, enc = None, None
        in_block = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith('SSID'):
                # "SSID 1 : NetworkName" or "SSID 2 :"
                after_colon = line.split(':', 1)[-1].strip() if ':' in line else ''
                if after_colon == ssid:
                    in_block = True
                    auth, enc = None, None
                elif in_block:
                    break
                continue
            if in_block:
                if 'Authentication' in line:
                    auth = line.split(':', 1)[-1].strip()
                elif 'Encryption' in line:
                    enc = line.split(':', 1)[-1].strip()
                if auth and enc:
                    return (auth, enc)
        return (auth, enc) if (auth or enc) else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _auth_enc_to_profile(auth: str | None, enc: str | None) -> tuple[str, str]:
    """Map scan result to WLAN profile auth/encryption values."""
    a = (auth or '').lower()
    if 'wpa3' in a or 'sae' in a:
        return ('WPA3SAE', 'AES')
    if 'wpa2' in a or 'psk' in a or 'personal' in a:
        return ('WPA2PSK', 'AES')
    if 'open' in a or not auth:
        return ('open', 'none')
    return ('WPA2PSK', 'AES')  # default fallback


def connect_hotspot_windows(ssid: str, password: str, skip_scan: bool = False) -> bool:
    """Connect to WiFi hotspot using netsh. Returns True on success.
    Auto-detects WPA2/WPA3/Open via scan unless skip_scan=True.
    """
    auth, enc = None, None
    if not skip_scan:
        scan_result = scan_network_security_windows(ssid)
        if scan_result:
            auth, enc = _auth_enc_to_profile(scan_result[0], scan_result[1])
            print(f'Detected: {scan_result[0]} / {scan_result[1]}')
    if auth is None:
        auth, enc = 'WPA2PSK', 'AES'
        print('Using WPA2-Personal (scan failed or network not in range)')
    ssid_esc = saxutils.escape(ssid)
    pass_esc = saxutils.escape(password)
    transition = ''
    if auth == 'WPA3SAE':
        transition = '\n<transitionMode xmlns="http://www.microsoft.com/networking/WLAN/profile/v4">true</transitionMode>'
    auth_enc = f'''<authEncryption>
<authentication>{auth}</authentication>
<encryption>{enc}</encryption>
<useOneX>false</useOneX>{transition}
</authEncryption>'''
    shared_key = ''
    if auth != 'open':
        shared_key = f'''<sharedKey>
<keyType>passPhrase</keyType>
<protected>false</protected>
<keyMaterial>{pass_esc}</keyMaterial>
</sharedKey>'''
    xml_content = f'''<?xml version="1.0" encoding="US-ASCII"?>
<WLANProfile xmlns="https://www.microsoft.com/networking/WLAN/profile/v1">
<name>{ssid_esc}</name>
<SSIDConfig>
<SSID>
<name>{ssid_esc}</name>
</SSID>
</SSIDConfig>
<connectionType>ESS</connectionType>
<connectionMode>auto</connectionMode>
<autoSwitch>false</autoSwitch>
<MSM>
<security>
{auth_enc}
{shared_key}
</security>
</MSM>
</WLANProfile>'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
        f.write(xml_content)
        profile_path = f.name
    try:
        add_result = subprocess.run(
            ['netsh', 'wlan', 'add', 'profile', f'filename={profile_path}'],
            capture_output=True, text=True, timeout=10
        )
        if add_result.returncode != 0 and 'already exists' not in (add_result.stderr or '').lower():
            print(f'netsh add profile failed: {add_result.stderr or add_result.stdout}')
            return False
        conn_result = subprocess.run(
            ['netsh', 'wlan', 'connect', f'name={ssid}', f'ssid={ssid}'],
            capture_output=True, text=True, timeout=30
        )
        if conn_result.returncode == 0:
            print(f'Connected to "{ssid}"')
            return True
        print(f'netsh connect failed: {conn_result.stderr or conn_result.stdout}')
        return False
    finally:
        try:
            os.unlink(profile_path)
        except OSError:
            pass


def connect_to_hotspot(ssid: str, password: str, interface: str | None = None, skip_scan: bool = False) -> bool:
    """Connect to WiFi hotspot. Returns True on success.
    Windows: scans to auto-detect WPA2/WPA3/Open unless skip_scan=True.
    Linux: iwctl auto-negotiates with the AP (no scan needed).
    """
    if sys.platform == 'win32':
        return connect_hotspot_windows(ssid, password, skip_scan)
    return connect_hotspot_linux(ssid, password, interface)


def run_create_ap():
    """Start create_ap (Arch/omarchy). Stops iwd first."""
    try:
        subprocess.run(['systemctl', 'stop', 'iwd'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    proc = subprocess.Popen(
        ['create_ap', '-n', 'wlan0', 'FlockYou-Hub'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode() if proc.stderr else ''
        raise RuntimeError(f'create_ap failed: {stderr}')
    return proc


def stop_create_ap():
    """Stop create_ap and restart iwd."""
    try:
        subprocess.run(['create_ap', '--stop', 'wlan0'], capture_output=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        subprocess.run(['systemctl', 'start', 'iwd'], capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def main():
    parser = argparse.ArgumentParser(
        description='Setup Wardriving',
        epilog='Examples: %(prog)s --hotspot --ssid "My Phone" --password mypass  |  On Windows, netsh may require Administrator.',
    )
    parser.add_argument('--hotspot', action='store_true', help='Skip ad-hoc WiFi; laptop joins phone hotspot')
    parser.add_argument('--ssid', metavar='SSID', help='Hotspot SSID to connect to (use with --hotspot and --password)')
    parser.add_argument('--password', metavar='PASS', help='Hotspot password (use with --ssid)')
    parser.add_argument('--interface', '-i', metavar='IFACE', help='WiFi interface (Linux only, e.g. wlan0)')
    parser.add_argument('--no-scan', action='store_true', help='Skip security scan (Windows); use WPA2-Personal. Use if network not in range yet.')
    parser.add_argument('--no-inhibit', action='store_true', help='Disable sleep inhibit (laptop may sleep during session)')
    args = parser.parse_args()

    create_ap_proc = None
    flock_proc = None

    def cleanup(signum=None, frame=None):
        nonlocal create_ap_proc, flock_proc
        if flock_proc and flock_proc.poll() is None:
            flock_proc.terminate()
            try:
                flock_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                flock_proc.kill()
        if create_ap_proc and create_ap_proc.poll() is None:
            create_ap_proc.terminate()
            try:
                create_ap_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                create_ap_proc.kill()
            stop_create_ap()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Connect to hotspot if SSID/password provided
    if args.ssid:
        if not args.password:
            print('--password required when using --ssid')
            sys.exit(1)
        if not connect_to_hotspot(args.ssid, args.password, args.interface, args.no_scan):
            sys.exit(1)
        time.sleep(2)  # Allow DHCP
    elif args.password and not args.ssid:
        print('--ssid required when using --password')
        sys.exit(1)

    # When connecting to hotspot, skip create_ap (we're joining a network, not creating one)
    use_hotspot_mode = args.hotspot or bool(args.ssid)

    if not use_hotspot_mode and sys.platform == 'linux':
        try:
            create_ap_proc = run_create_ap()
            print('Ad-hoc WiFi "FlockYou-Hub" started. Join from your phone.')
        except Exception as e:
            print(f'Ad-hoc WiFi failed: {e}. Use --hotspot to skip.')
            sys.exit(1)

    os.chdir(SCRIPT_DIR)
    sleep_cleanup = None if args.no_inhibit else enable_sleep_inhibit()
    flock_proc = run_flock_with_sleep_inhibit() if not args.no_inhibit else subprocess.Popen([sys.executable, FLOCKYOU_PY], cwd=SCRIPT_DIR)
    try:
        flock_proc.wait()
    finally:
        if sleep_cleanup:
            try:
                sleep_cleanup()
            except Exception:
                pass
    if create_ap_proc and create_ap_proc.poll() is None:
        create_ap_proc.terminate()
        stop_create_ap()


if __name__ == '__main__':
    main()
