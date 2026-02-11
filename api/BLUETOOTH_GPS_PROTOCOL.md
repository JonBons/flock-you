# Bluetooth GPS Protocol Specification (GPS2IP Compatible)

## Overview

This document specifies the Bluetooth Low Energy (BLE) protocol for transmitting GPS data from a phone to a Raspberry Pi running Flock You. **This implementation is compatible with GPS2IP**, a popular iOS app that shares GPS data via Bluetooth.

The protocol uses the **standard Bluetooth SIG Location and Navigation service** (UUID `0x1819`), ensuring compatibility with GPS2IP and other standard BLE GPS applications.

## BLE Service Specification

### Service UUID
- **Service UUID**: `00001819-0000-1000-8000-00805f9b34fb` (Location and Navigation Service - `0x1819`)
- **Standard**: Bluetooth SIG defined service

### Characteristics

#### 1. Location and Speed Characteristic
- **UUID**: `00002a67-0000-1000-8000-00805f9b34fb` (`0x2A67`)
- **Properties**: Read, Notify
- **Purpose**: Primary GPS coordinate and speed data
- **Data Format**: Binary (Bluetooth SIG specification)
  - Flags (1 byte): Bit flags indicating present fields
  - Latitude (4 bytes, int32): Degrees × 1e-7
  - Longitude (4 bytes, int32): Degrees × 1e-7
  - Elevation (2 bytes, int16): Meters
  - Speed (2 bytes, uint16): Meters per second × 1e-2
  - Heading (2 bytes, uint16): Degrees × 1e-2

#### 2. Navigation Characteristic
- **UUID**: `00002a68-0000-1000-8000-00805f9b34fb` (`0x2A68`)
- **Properties**: Read, Notify
- **Purpose**: Additional navigation data (bearing, distance, etc.)
- **Data Format**: Binary (Bluetooth SIG specification)

#### 3. LN Feature Characteristic
- **UUID**: `00002a6a-0000-1000-8000-00805f9b34fb` (`0x2A6A`)
- **Properties**: Read
- **Purpose**: Feature flags indicating supported capabilities
- **Data Format**: 32-bit value (4 bytes)

## Data Flow

1. **Phone App (GPS2IP or compatible)**:
   - **No WiFi or network access required!**
   - Connects to Raspberry Pi via BLE (Bluetooth only)
   - Reads GPS location periodically (every 1-5 seconds)
   - Sends GPS data via Location and Speed Characteristic notifications
   - Uses standard Bluetooth SIG format (binary, not JSON)
   - Handles reconnection automatically

2. **Raspberry Pi**:
   - Advertises BLE service as "GPS2IP" (via `ble_gps_receiver.py`)
   - Accepts connections from phone via Bluetooth
   - Subscribes to Location and Speed Characteristic notifications
   - Parses binary Bluetooth SIG format and converts to internal format
   - Integrates GPS data with Flock You API
   - Maintains connection and handles disconnections

**Note**: The phone connects directly via Bluetooth - it does NOT need WiFi, internet, or access to the web API. The API endpoints (`/api/ble-gps/*`) are only for managing the BLE receiver from a laptop/computer that IS connected to the same network (for the web dashboard).

## GPS2IP Compatibility

This implementation is **fully compatible with GPS2IP** (iOS app). Users can:
1. Install GPS2IP on their iPhone
2. Start GPS2IP and enable Bluetooth mode
3. Connect to the Raspberry Pi running Flock You
4. GPS data will automatically flow to Flock You

No custom phone app development required - GPS2IP works out of the box!

## Connection Parameters

- **Connection Interval**: 7.5ms - 4s (negotiated)
- **Supervision Timeout**: 6s
- **MTU Size**: 512 bytes (for larger JSON payloads)
- **Security**: "Just Works" pairing (no PIN code required)

## Pairing Process

### BLE "Just Works" Pairing

Bluetooth Low Energy uses **"Just Works" pairing**, which means:

- **No PIN Code Required**: Devices connect without entering a PIN
- **Automatic Pairing**: Pairing happens automatically when devices connect
- **No User Input**: No manual pairing steps needed

### How It Works

1. **GPS2IP App Scans**: App scans for BLE devices advertising "GPS2IP"
2. **Device Found**: App discovers the Raspberry Pi
3. **Connection Initiated**: App connects to the Location and Navigation service
4. **Automatic Pairing**: BLE "Just Works" pairing occurs automatically
5. **iOS Note**: iOS may show a brief confirmation alert (no PIN needed)
6. **Connected**: Devices are paired and GPS data flows

### Security Considerations

- **Local Range**: BLE has limited range (~10 meters), providing natural security
- **No Encryption by Default**: Current implementation uses unencrypted BLE (can be added if needed)
- **Pairing Security**: "Just Works" is secure for local, short-range connections
- **Optional Bonding**: Devices can optionally bond (remember pairing) for faster reconnection

### iOS Pairing Behavior

On iOS devices (like iPhone with GPS2IP):
- May show a brief system alert: "Pair with GPS2IP?"
- User taps "Pair" (no PIN code to enter)
- This is a one-time confirmation
- After pairing, reconnections are automatic

### Android Pairing Behavior

On Android devices:
- Typically pairs automatically without any user interaction
- No confirmation dialog in most cases
- Seamless connection experience

## Error Handling

- **Connection Loss**: Automatic reconnection attempts (exponential backoff)
- **Invalid Data**: Log error, request new GPS reading
- **No GPS Fix**: Phone app should not send data if GPS fix quality is poor

## Phone App Requirements (Future)

The phone app should:
1. Request location permissions (background location)
2. Use Core Location (iOS) or LocationManager (Android) for GPS
3. Connect to Raspberry Pi BLE service
4. Send GPS updates every 1-5 seconds when location changes
5. Handle background operation (iOS: Background Modes, Android: Foreground Service)
6. Implement exponential backoff for reconnection

## Raspberry Pi Requirements

- Bluetooth 4.0+ (BLE support)
- Python 3.8+
- `bleak` library for BLE communication
- `bluez` system package (Linux Bluetooth stack)

## Advantages Over Web-Based GPS

1. **Background Operation**: No browser required, works when phone is locked
2. **Battery Efficient**: BLE uses less power than WiFi/HTTP polling
3. **Reliable**: Direct connection, no network dependency
4. **Lower Latency**: Direct BLE communication is faster
5. **No HTTPS Required**: No certificate management needed
