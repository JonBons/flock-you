# Wardriving Setup Instructions

This guide provides manual instructions for setting up wardriving mode with Flock You.

## Overview

Wardriving mode allows you to use your phone's GPS (iPhone or Android) along with your laptop/Raspberry Pi and ESP32 device for mobile surveillance detection. The setup involves:

1. **Connecting to your phone's Personal Hotspot** (recommended)
2. **Preventing your device from sleeping** during the session (not needed for Raspberry Pi)
3. **Starting the Flock You server** with HTTPS support (required for iOS location services)

**Note:** Raspberry Pi users should use command-line methods and access the web interface via the Pi's IP address instead of `localhost`. See [Raspberry Pi Notes](#raspberry-pi-specific-notes) below.

## Prerequisites

- ESP32 device connected to laptop/Raspberry Pi via USB
- Phone with Personal Hotspot capability
- Python 3.8+ installed
- Flock You dependencies installed (`pip install -r requirements.txt`)

---

## Quick Setup Guide

### Step 1: Enable Personal Hotspot on Your Phone

**iPhone:** Settings → Personal Hotspot → Toggle ON (note the password)

**Android:** Settings → Network & internet → Hotspot & tethering → Wi‑Fi hotspot → Toggle ON

### Step 2: Connect Device to Hotspot

#### Windows (Laptop)
Click the WiFi icon → Find your phone's hotspot → Connect → Enter password

#### Linux / Raspberry Pi
```bash
nmcli device wifi connect "YourPhoneSSID" password "password"
```

**Note:** If using a desktop environment, you can also use the network icon in the system tray.

### Step 3: Prevent Device Sleep

**Windows:** Settings → System → Power & sleep → Set sleep to **Never** (when plugged in)

**Linux:** Run the server with sleep prevention:
```bash
cd api
systemd-inhibit --what=sleep:idle python3 flockyou.py --https
```

**Raspberry Pi:** Skip this step (Pi doesn't sleep by default)

### Step 4: Start Flock You Server

```bash
cd api
python3 flockyou.py --https
```

### Step 5: Connect Phone to Web Interface

1. **Find your device's IP address:**
   - **Laptop:** Use `localhost` or `127.0.0.1`
   - **Raspberry Pi:** Run `hostname -I` to find the IP (e.g., `192.168.43.123`)

2. **On your phone** (connected to the same hotspot), open:
   - Laptop: `https://localhost:5000/connect`
   - Raspberry Pi: `https://[PI_IP]:5000/connect` (e.g., `https://192.168.43.123:5000/connect`)

3. **Scan the QR code** or note the URL shown

4. **Open that URL** in your phone's browser

5. **iOS users:** Accept the "connection not private" warning (tap Advanced → Proceed)

6. **Allow GPS access** when prompted

### Step 6: Disable Phone Display Sleep

**iPhone:** Settings → Display & Brightness → Auto-Lock → **Never**

**Android:** Settings → Display → Screen timeout → **Never**

### Step 7: Connect ESP32 Device

1. In the web interface, find your ESP32 in the serial device list
2. Click "Connect"

**Raspberry Pi users:** Ensure USB permissions: `sudo usermod -aG dialout $USER` (then logout/login)

---

## Alternative: Creating Ad-Hoc WiFi Network (Linux Only)

**Not recommended** if using CarPlay/Android Auto. This method creates a WiFi access point that your phone joins.

### Using nmcli (Simplest)
```bash
nmcli connection add type wifi ifname wlan0 con-name FlockYou-Hub \
    autoconnect yes ssid FlockYou-Hub mode ap \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "password"
nmcli connection up FlockYou-Hub
```

Then join "FlockYou-Hub" from your phone's WiFi settings and follow Steps 3-7 above.

**Advanced options:** See [Troubleshooting](#troubleshooting) for hostapd and other methods.

---

## Troubleshooting

### Connection Issues

**Can't connect to hotspot:**
- **Windows:** Check WiFi adapter is enabled: `netsh wlan show interfaces`
- **Linux/Pi:** Check interface name: `ip link show` (may be `wlan0`, `wlan1`, etc.)
- **Linux/Pi:** Check if blocked: `rfkill list` → `sudo rfkill unblock wifi`
- **Linux/Pi:** Verify connection: `nmcli device status` or `ip addr show wlan0`

**Advanced Linux connection methods** (if nmcli doesn't work):
- **wpa_supplicant:** Create `/etc/wpa_supplicant/hotspot.conf` with `network={ssid="YourPhoneSSID" psk="password"}` then run `sudo wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/hotspot.conf && sudo dhclient wlan0`
- **iwd (Arch):** `iwctl` → `station wlan0 scan` → `station wlan0 connect "YourPhoneSSID"`

**Windows command-line** (if GUI doesn't work):
- See [Advanced Windows Connection](#advanced-windows-connection) below

### Sleep Prevention Not Working

**Windows:**
- Use command line: `powercfg /change standby-timeout-ac 0`
- Ensure laptop is plugged in

**Linux:**
- If systemd-inhibit doesn't work, use GUI: Settings → Power → Automatic Suspend → Off
- Or temporarily disable: `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`

### Server Won't Start

- Ensure you're in the `api` directory
- Check Python version: `python3 --version` (needs 3.8+)
- Verify dependencies: `pip install -r requirements.txt`
- Check if port 5000 is in use: `netstat -an | grep 5000` (Linux) or `netstat -an | findstr 5000` (Windows)
- **Raspberry Pi:** Ensure firewall allows port 5000: `sudo ufw allow 5000` (if using ufw)

### Can't Access Web Interface from Phone

- **Raspberry Pi:** Ensure phone and Pi are on the same network (same hotspot)
- **Raspberry Pi:** Find Pi's IP: `hostname -I` or `ip addr show wlan0 | grep "inet "`
- **Raspberry Pi:** Access via `https://[PI_IP]:5000` not `localhost`
- Check firewall settings

### ESP32 Not Connecting

- Verify USB connection
- Check device appears in serial port list
- Try different USB port/cable
- **Linux/Pi:** Check permissions: `sudo usermod -aG dialout $USER` (logout/login)
- **Raspberry Pi:** List devices: `lsusb` and ports: `ls /dev/ttyUSB*` or `ls /dev/ttyACM*`
- **Raspberry Pi:** Check detection: `dmesg | tail` after plugging in USB

### HTTPS Certificate Warning (iOS)

This is **normal and expected**. iOS requires HTTPS for location services, but the self-signed certificate triggers a warning. Tap "Advanced" → "Proceed" to continue.

---

## Advanced Windows Connection

If the GUI method doesn't work, use netsh:

1. Open PowerShell **as Administrator**
2. Scan: `netsh wlan show networks`
3. Create `hotspot.xml`:
   ```xml
   <?xml version="1.0" encoding="US-ASCII"?>
   <WLANProfile xmlns="https://www.microsoft.com/networking/WLAN/profile/v1">
   <name>YourPhoneSSID</name>
   <SSIDConfig><SSID><name>YourPhoneSSID</name></SSID></SSIDConfig>
   <connectionType>ESS</connectionType>
   <connectionMode>auto</connectionMode>
   <MSM>
     <security>
       <authEncryption>
         <authentication>WPA2PSK</authentication>
         <encryption>AES</encryption>
         <useOneX>false</useOneX>
       </authEncryption>
       <sharedKey>
         <keyType>passPhrase</keyType>
         <protected>false</protected>
         <keyMaterial>password</keyMaterial>
       </sharedKey>
     </security>
   </MSM>
   </WLANProfile>
   ```
4. Add profile: `netsh wlan add profile filename=hotspot.xml`
5. Connect: `netsh wlan connect name=YourPhoneSSID`

**WPA3:** Change `WPA2PSK` to `WPA3SAE` and add `<transitionMode xmlns="http://www.microsoft.com/networking/WLAN/profile/v4">true</transitionMode>` before `</authEncryption>`.

---

## Raspberry Pi Specific Notes

### Headless Setup

- **SSH Access:** `sudo systemctl enable ssh && sudo systemctl start ssh`
- **Finding IP:** `hostname -I` or `ip addr show wlan0 | grep "inet "`
- **Web Access:** Use `https://[PI_IP]:5000` instead of `localhost`
- **Power:** Use 2.5A+ power supply to prevent USB issues with ESP32
- **USB Serial:** ESP32 appears as `/dev/ttyUSB0` or `/dev/ttyACM0`
- **No Sleep:** Pi doesn't sleep by default, so sleep prevention is optional
- **Command Line Only:** Use `nmcli` for WiFi connections (no GUI options)

### USB Permissions

```bash
sudo usermod -aG dialout $USER
# Logout and login for changes to take effect
```

---

## Session Files

Detection data is automatically saved to:
- `api/exports/session_YYYYMMDD_HHMMSS.csv`
- `api/exports/session_YYYYMMDD_HHMMSS.kml`

These files contain all detections with timestamps and GPS coordinates (if phone GPS is connected).

---

## Cleanup After Session

**Windows:** Restore power settings:
```powershell
powercfg /change standby-timeout-ac 30
powercfg /change monitor-timeout-ac 10
```

**Linux:** If you stopped services or masked sleep targets:
```bash
sudo systemctl start NetworkManager  # if stopped
sudo systemctl start iwd  # if stopped
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target  # if masked
```

---

## Recommended Setup for CarPlay/Android Auto

1. Use **Phone Hotspot** method (keeps phone WiFi free)
2. Connect phone to car via **USB cable** for CarPlay/Android Auto
3. Use car's display for maps/navigation
4. Use phone's browser for Flock You interface
5. Laptop/Raspberry Pi runs the server and connects to phone's hotspot

This maximizes functionality: maps on car display, Flock You on phone, and stable WiFi connection between all devices.
