# Bluetooth GPS Setup Guide

This guide explains how to set up Bluetooth GPS using a phone connected to a Raspberry Pi running Flock You.

## Overview

Instead of using the phone's browser with HTTPS for GPS data, you can use Bluetooth Low Energy (BLE) to send GPS data directly from your phone to the Raspberry Pi. This approach offers several advantages:

- **Background Operation**: Works when phone is locked or browser is closed
- **No WiFi Required**: Phone doesn't need to be on any network - direct Bluetooth connection
- **Battery Efficient**: BLE uses less power than WiFi/HTTP polling
- **No HTTPS Required**: No certificate management needed
- **More Reliable**: Direct connection, no network dependency
- **Lower Latency**: Direct BLE communication is faster

### Architecture

```
Phone (No WiFi)          Raspberry Pi (BLE Server)          Laptop (Web Interface)
     |                              |                                |
     |  BLE Connection              |                                |
     |<---------------------------->|                                |
     |                              |                                |
     |  GPS Data (BLE)              |                                |
     |------------------------------>|                                |
     |                              |                                |
     |                              |<----------------HTTP API--------|
     |                              |  (Start/Stop/Status)            |
     |                              |                                |
```

**Important**: The phone connects directly via Bluetooth - it does NOT need WiFi or access to the web API. The API endpoints (`/api/ble-gps/*`) are only for managing the BLE receiver from a laptop or other device that IS connected to the same network as the Raspberry Pi (for the web dashboard).

## Prerequisites

### Raspberry Pi Requirements

1. **Raspberry Pi** with Bluetooth 4.0+ (BLE support)
   - Raspberry Pi 3, 4, or newer recommended
   - Built-in Bluetooth or USB Bluetooth dongle with BLE support

2. **Operating System**: Raspberry Pi OS (Debian-based Linux)

3. **Python 3.8+** installed

4. **Bluetooth Stack**: bluez (usually pre-installed)

### Software Installation

1. **Install system dependencies**:
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3-pip python3-venv bluez libbluetooth-dev
   ```

2. **Enable Bluetooth** (if not already enabled):
   ```bash
   sudo systemctl enable bluetooth
   sudo systemctl start bluetooth
   ```

3. **Install Python dependencies**:
   ```bash
   cd api
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   This will install `bleak` (BLE library) along with other dependencies.

4. **Verify Bluetooth is working**:
   ```bash
   bluetoothctl
   # In bluetoothctl:
   power on
   show
   exit
   ```

## Raspberry Pi Setup

### Option 1: Auto-Start on Boot (Recommended for Raspberry Pi Zero 2 W)

For headless operation where the Pi starts automatically on power-up:

Quick setup:
```bash
# Install systemd service
sudo cp flockyou.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable flockyou.service
sudo systemctl start flockyou.service
```

After setup, the Pi will automatically:
- Start Flock You server on boot
- Start BLE GPS receiver and begin advertising
- Be ready for GPS2IP connections immediately

### Option 2: Manual Start

### 1. Start Flock You Server

```bash
cd api
source venv/bin/activate
python3 flockyou.py --ble-gps
```

The `--ble-gps` flag automatically starts the BLE GPS receiver.

### 2. Enable BLE GPS Receiver (if not using --ble-gps flag)

**Note**: The phone connects directly via Bluetooth - it does NOT need WiFi or access to the API. These API endpoints are for managing the BLE receiver from a laptop/computer (for the web dashboard).

#### Option A: Via Web Interface (from laptop/computer)

1. On a laptop/computer connected to the same network as the Pi, open: `http://[PI_IP]:5000`
2. Navigate to the GPS connection section
3. Click "Start BLE GPS Receiver"
4. The Pi will start advertising the BLE service as: `GPS2IP`
5. Now GPS2IP (or compatible app) can connect via Bluetooth (no WiFi needed)

#### Option B: Via API (from laptop/computer)

```bash
# From a laptop/computer on the same network
curl -X POST http://[PI_IP]:5000/api/ble-gps/connect
```

#### Option C: Command Line (on Raspberry Pi directly)

```bash
# SSH into the Pi and use Python directly
python3 -c "from ble_gps_receiver import start_ble_gps_receiver, handle_ble_gps_update; start_ble_gps_receiver()"
```

### 3. Check BLE GPS Status

```bash
curl http://localhost:5000/api/ble-gps/status
```

Response:
```json
{
  "available": true,
  "enabled": true,
  "connected": false,
  "connected_devices": 0,
  "latest_gps": null
}
```

## Phone App Setup

### Option 1: Use GPS2IP (Recommended - No Development Required!)

**GPS2IP** is a popular iOS app that works out of the box with this implementation. No custom app development needed!

1. **Install GPS2IP** from the App Store on your iPhone
2. **Open GPS2IP** and enable Bluetooth mode
3. **Start the BLE GPS receiver** on Raspberry Pi (see above)
4. **In GPS2IP**, scan for devices and connect to "GPS2IP"
5. **Pairing**: 
   - iOS may show "Pair with GPS2IP?" alert - tap "Pair" (no PIN code needed!)
   - This is a one-time confirmation
6. GPS data will automatically flow to Flock You!

**Important**: 
- Phone doesn't need WiFi - only Bluetooth!
- **No PIN code required** - BLE uses "Just Works" pairing (see Pairing section below)

### Option 2: Build Custom App (Future)

If you want to build a custom app, it should:

1. **Request Permissions**:
   - Location permissions (including background location)
   - Bluetooth permissions
   - Background app refresh

2. **Connect to Raspberry Pi via Bluetooth**:
   - Scan for BLE device: `GPS2IP`
   - Connect to service UUID: `00001819-0000-1000-8000-00805f9b34fb` (Location and Navigation)
   - Subscribe to notifications on: `00002a67-0000-1000-8000-00805f9b34fb` (Location and Speed)
   - **No WiFi or network access required!**

3. **Send GPS Data**:
   - Read GPS location every 1-5 seconds (or on location change)
   - Format as Bluetooth SIG binary format (not JSON):
     - Flags byte
     - Latitude (int32, degrees × 1e-7)
     - Longitude (int32, degrees × 1e-7)
     - Elevation (int16, meters)
     - Speed (uint16, m/s × 1e-2)
     - Heading (uint16, degrees × 1e-2)
   - Send via Location and Speed Characteristic notifications

4. **Handle Background Operation**:
   - **iOS**: Use Background Modes → Location updates
   - **Android**: Use Foreground Service with location updates

5. **Reconnection Logic**:
   - Automatically reconnect if connection is lost
   - Exponential backoff for reconnection attempts

## Testing Without Phone App

Until the phone app is built, you can test the BLE GPS receiver using:

### Option 1: BLE Scanner App

Use a BLE scanner app on your phone (like nRF Connect or LightBlue) to:

1. Scan for `FlockYou-GPS-Receiver`
2. Connect to the service
3. Manually write test GPS data to the GPS Data Characteristic

### Option 2: Python Test Script

Create a test script to simulate a phone sending GPS data:

```python
import asyncio
from bleak import BleakClient

GPS_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
GPS_DATA_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

async def send_test_gps():
    # Scan for device
    devices = await BleakScanner.discover()
    target = None
    for d in devices:
        if "FlockYou" in d.name:
            target = d
            break
    
    if not target:
        print("FlockYou-GPS-Receiver not found")
        return
    
    # Connect and send GPS data
    async with BleakClient(target.address) as client:
        test_gps = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 52.5,
            "accuracy": 10.0,
            "timestamp": "2026-02-09T12:34:56.789Z"
        }
        json_data = json.dumps(test_gps).encode('utf-8')
        await client.write_gatt_char(GPS_DATA_CHAR_UUID, json_data)
        print("GPS data sent!")

asyncio.run(send_test_gps())
```

## Troubleshooting

### BLE GPS Receiver Won't Start

1. **Check Bluetooth is enabled**:
   ```bash
   bluetoothctl show
   ```

2. **Check permissions**:
   ```bash
   # Ensure user is in bluetooth group
   sudo usermod -aG bluetooth $USER
   # Logout and login again
   ```

3. **Check bluez version**:
   ```bash
   bluetoothctl --version
   # Should be 5.50+ for full BLE support
   ```

4. **Check bleak installation**:
   ```bash
   pip show bleak
   # Should be 0.20.0 or newer
   ```

### Phone Can't Find Raspberry Pi

1. **Ensure BLE GPS receiver is started**:
   ```bash
   curl http://localhost:5000/api/ble-gps/status
   ```

2. **Check Raspberry Pi is advertising**:
   ```bash
   # On another device, scan for BLE devices
   # Should see "GPS2IP" (GPS2IP-compatible name)
   ```

3. **Check Bluetooth is not blocked**:
   ```bash
   rfkill list
   # If blocked, unblock:
   sudo rfkill unblock bluetooth
   ```

4. **If using GPS2IP app**:
   - Ensure GPS2IP is in Bluetooth mode (not TCP/UDP mode)
   - Check that GPS2IP is advertising (flashing Bluetooth icon)
   - Try restarting GPS2IP app

### Connection Drops Frequently

1. **Check Bluetooth signal strength** (keep phone close to Pi)
2. **Check for interference** (other Bluetooth devices, WiFi)
3. **Increase connection interval** (phone app setting)
4. **Check Pi power supply** (low power can cause Bluetooth issues)

### GPS Data Not Being Received

1. **Check BLE GPS status**:
   ```bash
   curl http://localhost:5000/api/ble-gps/status
   ```

2. **Check server logs** for GPS updates:
   ```bash
   # Look for "BLE GPS:" messages in server output
   ```

3. **Verify GPS data format** (must be valid JSON with latitude/longitude)

4. **Check phone app is sending data** (verify in phone app logs)

## API Endpoints

### Start BLE GPS Receiver
```bash
POST /api/ble-gps/connect
```

### Stop BLE GPS Receiver
```bash
POST /api/ble-gps/disconnect
```

### Get BLE GPS Status
```bash
GET /api/ble-gps/status
```

Response:
```json
{
  "available": true,
  "enabled": true,
  "connected": true,
  "connected_devices": 1,
  "latest_gps": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude": 52.5,
    "timestamp": "2026-02-09T12:34:56.789Z",
    "fix_quality": 1,
    "satellites": 0,
    "system_timestamp": 1707483296.789,
    "accuracy": 10.0,
    "source": "bluetooth"
  }
}
```

## Integration with Existing GPS System

The BLE GPS receiver integrates seamlessly with the existing GPS system:

- GPS data from BLE is added to `gps_history` for temporal matching
- Detections automatically use BLE GPS data when available
- Works alongside serial GPS dongle (if connected)
- WebSocket GPS (browser) still works as fallback

The system prioritizes GPS data in this order:
1. BLE GPS (if connected)
2. Serial GPS dongle (if connected)
3. WebSocket GPS (browser, if connected)

## Pairing Process

### No PIN Code Required!

BLE uses **"Just Works" pairing** - no PIN code, no passkey, no manual pairing steps needed. The connection happens automatically.

### How Pairing Works

1. **GPS2IP App Scans**: App scans for BLE devices advertising "GPS2IP"
2. **Device Found**: App discovers the Raspberry Pi
3. **Connection Initiated**: App connects to the Location and Navigation service
4. **Automatic Pairing**: BLE "Just Works" pairing occurs automatically
5. **iOS Note**: iOS may show a brief confirmation alert "Pair with GPS2IP?" - just tap "Pair" (no PIN needed)
6. **Connected**: Devices are paired and GPS data flows

### Platform-Specific Behavior

**iOS (iPhone/iPad):**
- First connection: May show "Pair with GPS2IP?" alert - tap "Pair" (one-time)
- Subsequent connections: Automatic, no dialog

**Android:**
- Usually pairs automatically without any user interaction
- Seamless connection experience

After first pairing, devices are "bonded" (remembered) and reconnect automatically.

## Reconnection Handling

### Automatic Reconnection

The BLE GPS receiver handles disconnections gracefully:

**When Device Disconnects:**
- Device is removed from connected devices
- BLE server **continues advertising** (ready for reconnection)
- Latest GPS data is retained
- Logs disconnection event

**When Device Reconnects:**
- GPS2IP automatically reconnects when:
  - App detects device is available
  - Bluetooth is re-enabled
  - Device comes back into range
- Connection is seamless - GPS data flow resumes immediately
- No manual intervention needed

**Key Points:**
- Server always advertising - ready for connections
- Client initiates reconnection automatically
- Multiple devices can connect simultaneously
- No data loss during disconnection

## Security Considerations

- **Local Range**: BLE has limited range (~10 meters), providing natural security
- **No Encryption**: Currently unencrypted (acceptable for GPS coordinates, can be added if needed)
- **Pairing Security**: "Just Works" is secure for local short-range connections
- **Bonding**: Devices remember each other for faster reconnection

## Protocol Reference

See [BLUETOOTH_GPS_PROTOCOL.md](BLUETOOTH_GPS_PROTOCOL.md) for complete technical protocol specification.
