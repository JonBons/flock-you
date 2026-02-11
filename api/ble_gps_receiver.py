"""
Bluetooth Low Energy GPS Receiver for Flock You

This module handles BLE connections from phones and receives GPS data.
It integrates with the main Flock You API to provide GPS coordinates for detections.
"""

import asyncio
import json
import time
import logging
from datetime import datetime
from typing import Optional, Callable

try:
    # Try importing bleak components
    from bleak import BleakScanner
    # Note: BleakServer may not be available in all bleak versions
    # We'll use a simpler approach with bluez D-Bus if needed
    try:
        from bleak import BleakServer
        from bleak.backends.characteristic import BleakGATTCharacteristicProperties
        BLEAK_SERVER_AVAILABLE = True
    except ImportError:
        BLEAK_SERVER_AVAILABLE = False
        print("Warning: BleakServer not available. Using alternative BLE server implementation.")
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    print("Warning: bleak library not installed. BLE GPS receiver will not work.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# BLE Service and Characteristic UUIDs (GPS2IP compatible)
# Using standard Bluetooth SIG Location and Navigation service
GPS_SERVICE_UUID = "00001819-0000-1000-8000-00805f9b34fb"  # Location and Navigation (0x1819)
LOCATION_SPEED_CHAR_UUID = "00002a67-0000-1000-8000-00805f9b34fb"  # Location and Speed (0x2A67)
NAVIGATION_CHAR_UUID = "00002a68-0000-1000-8000-00805f9b34fb"  # Navigation (0x2A68)
LN_FEATURE_CHAR_UUID = "00002a6a-0000-1000-8000-00805f9b34fb"  # LN Feature (0x2A6A)

# Device name for advertising (GPS2IP compatible)
DEVICE_NAME = "GPS2IP"  # Use GPS2IP name for compatibility


class BLEGPSReceiver:
    """
    BLE GPS Receiver that advertises a service and receives GPS data from phones.
    
    Note: This implementation uses bluez D-Bus API for GATT server functionality,
    as bleak's BleakServer may not be available on all platforms.
    """
    
    def __init__(self, gps_callback: Optional[Callable] = None, connection_callback: Optional[Callable] = None):
        """
        Initialize the BLE GPS Receiver.
        
        Args:
            gps_callback: Optional callback function that receives GPS data dict
                         Format: {'latitude': float, 'longitude': float, ...}
            connection_callback: Optional callback function called on connection changes
                                Format: callback(event_type: str, device_address: str, connected_count: int)
                                event_type: 'connected' or 'disconnected'
        """
        self.gps_callback = gps_callback
        self.connection_callback = connection_callback
        self.server = None
        self.connected_devices = set()
        self.is_running = False
        self.latest_gps_data = None
        self.last_connection_state = False  # Track previous connection state
        
        if not BLEAK_AVAILABLE:
            raise ImportError("bleak library is required for BLE GPS receiver")
        
    def _parse_location_speed_characteristic(self, data: bytearray) -> Optional[dict]:
        """
        Parse Bluetooth SIG Location and Speed Characteristic (0x2A67) data.
        
        Format according to Bluetooth SIG specification:
        - Flags (1 byte): Bit flags indicating which fields are present
        - Latitude (4 bytes, int32): Degrees * 1e-7
        - Longitude (4 bytes, int32): Degrees * 1e-7
        - Elevation (2 bytes, int16): Meters
        - Speed (2 bytes, uint16): Meters per second * 1e-2
        - Heading (2 bytes, uint16): Degrees * 1e-2
        - ... (other optional fields based on flags)
        
        Returns parsed GPS data dict or None if invalid.
        """
        try:
            if len(data) < 11:  # Minimum size for required fields
                logger.warning(f"Location and Speed data too short: {len(data)} bytes")
                return None
            
            # Parse flags (first byte)
            flags = data[0]
            has_latitude = (flags & 0x01) != 0
            has_longitude = (flags & 0x02) != 0
            has_elevation = (flags & 0x04) != 0
            has_speed = (flags & 0x08) != 0
            has_heading = (flags & 0x10) != 0
            
            offset = 1
            gps_data = {}
            
            # Parse latitude (int32, degrees * 1e-7)
            if has_latitude and len(data) >= offset + 4:
                lat_raw = int.from_bytes(data[offset:offset+4], byteorder='little', signed=True)
                gps_data['latitude'] = round(lat_raw / 1e7, 8)
                offset += 4
            else:
                logger.warning("Missing latitude in Location and Speed data")
                return None
            
            # Parse longitude (int32, degrees * 1e-7)
            if has_longitude and len(data) >= offset + 4:
                lon_raw = int.from_bytes(data[offset:offset+4], byteorder='little', signed=True)
                gps_data['longitude'] = round(lon_raw / 1e7, 8)
                offset += 4
            else:
                logger.warning("Missing longitude in Location and Speed data")
                return None
            
            # Parse elevation (int16, meters)
            if has_elevation and len(data) >= offset + 2:
                elevation_raw = int.from_bytes(data[offset:offset+2], byteorder='little', signed=True)
                gps_data['altitude'] = round(float(elevation_raw), 3)
                offset += 2
            else:
                gps_data['altitude'] = 0.0
            
            # Parse speed (uint16, m/s * 1e-2)
            if has_speed and len(data) >= offset + 2:
                speed_raw = int.from_bytes(data[offset:offset+2], byteorder='little', signed=False)
                gps_data['speed'] = round(speed_raw / 1e2, 2)  # m/s
                offset += 2
            else:
                gps_data['speed'] = 0.0
            
            # Parse heading (uint16, degrees * 1e-2)
            if has_heading and len(data) >= offset + 2:
                heading_raw = int.from_bytes(data[offset:offset+2], byteorder='little', signed=False)
                gps_data['heading'] = round(heading_raw / 1e2, 2)  # degrees
                offset += 2
            else:
                gps_data['heading'] = 0.0
            
            # Validate coordinates
            lat = gps_data['latitude']
            lon = gps_data['longitude']
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                logger.warning(f"Invalid GPS coordinates: lat={lat}, lon={lon}")
                return None
            
            # Add metadata
            gps_data['timestamp'] = datetime.now().isoformat()
            gps_data['system_timestamp'] = time.time()
            gps_data['fix_quality'] = 1  # Assume good fix from GPS2IP
            gps_data['satellites'] = 0  # Not provided in this characteristic
            gps_data['source'] = 'bluetooth_gps2ip'
            
            return gps_data
            
        except Exception as e:
            logger.error(f"Error parsing Location and Speed characteristic: {e}")
            return None
    
    async def location_speed_handler(self, sender, data: bytearray):
        """
        Handle Location and Speed Characteristic (0x2A67) notifications from GPS2IP.
        
        Args:
            sender: The characteristic that sent the data
            data: Raw byte data in Bluetooth SIG Location and Speed format
        """
        gps_data = self._parse_location_speed_characteristic(data)
        if not gps_data:
            return
        
        # Store latest GPS data
        self.latest_gps_data = gps_data
        
        # Log GPS update
        logger.info(
            f"GPS2IP Update: {gps_data['latitude']:.6f}, "
            f"{gps_data['longitude']:.6f} "
            f"(alt: {gps_data.get('altitude', 0):.1f}m, "
            f"speed: {gps_data.get('speed', 0):.1f}m/s)"
        )
        
        # Call callback if provided
        if self.gps_callback:
            try:
                self.gps_callback(gps_data)
            except Exception as e:
                logger.error(f"Error in GPS callback: {e}")
    
    async def navigation_handler(self, sender, data: bytearray):
        """
        Handle Navigation Characteristic (0x2A68) notifications from GPS2IP.
        This contains additional navigation data (bearing, distance, etc.)
        """
        # Navigation characteristic is optional - log if received
        logger.debug(f"Navigation characteristic data received: {len(data)} bytes")
        # We primarily use Location and Speed, but could parse this for additional data
    
    async def ln_feature_read_handler(self, sender) -> bytearray:
        """
        Handle read requests for LN Feature Characteristic (0x2A6A).
        
        Returns feature flags indicating which features are supported.
        According to Bluetooth SIG spec, this is a 32-bit value.
        """
        # Feature flags: bit 0 = Instantaneous Speed, bit 1 = Total Distance, etc.
        # For GPS2IP compatibility, we support Location and Speed
        features = 0x01  # Instantaneous Speed supported
        return features.to_bytes(4, byteorder='little')
    
    async def start_server(self):
        """
        Start the BLE server and begin advertising.
        
        Note: This uses bluez D-Bus API directly for better compatibility.
        """
        if self.is_running:
            logger.warning("BLE server already running")
            return
        
        if not BLEAK_SERVER_AVAILABLE:
            # Fallback: Use bluez D-Bus API directly
            logger.info("Using bluez D-Bus API for BLE server")
            try:
                await self._start_bluez_server()
                return
            except Exception as e:
                logger.error(f"Failed to start bluez server: {e}")
                raise
        
        try:
            # Create BLE server using GPS2IP-compatible service (Location and Navigation)
            self.server = BleakServer(
                name=DEVICE_NAME,
                services=[
                    {
                        "uuid": GPS_SERVICE_UUID,  # 0x1819 Location and Navigation
                        "characteristics": [
                            {
                                "uuid": LOCATION_SPEED_CHAR_UUID,  # 0x2A67
                                "properties": BleakGATTCharacteristicProperties(
                                    read=True, notify=True
                                ),
                                "descriptors": [],
                            },
                            {
                                "uuid": NAVIGATION_CHAR_UUID,  # 0x2A68
                                "properties": BleakGATTCharacteristicProperties(
                                    read=True, notify=True
                                ),
                                "descriptors": [],
                            },
                            {
                                "uuid": LN_FEATURE_CHAR_UUID,  # 0x2A6A
                                "properties": BleakGATTCharacteristicProperties(
                                    read=True
                                ),
                                "descriptors": [],
                            },
                        ],
                    }
                ],
            )
            
            # Set up characteristic handlers for GPS2IP
            self.server.set_notify_handler(LOCATION_SPEED_CHAR_UUID, self.location_speed_handler)
            self.server.set_notify_handler(NAVIGATION_CHAR_UUID, self.navigation_handler)
            self.server.set_read_handler(LN_FEATURE_CHAR_UUID, self.ln_feature_read_handler)
            
            # Set up connection/disconnection handlers
            self.server.set_connection_handler(self._on_connect)
            self.server.set_disconnection_handler(self._on_disconnect)
            
            # Start advertising
            await self.server.start()
            self.is_running = True
            
            logger.info(f"BLE GPS Receiver started (GPS2IP compatible)")
            logger.info(f"Device name: {DEVICE_NAME}")
            logger.info(f"Service UUID: {GPS_SERVICE_UUID} (Location and Navigation)")
            logger.info(f"Characteristics:")
            logger.info(f"  - Location and Speed: {LOCATION_SPEED_CHAR_UUID}")
            logger.info(f"  - Navigation: {NAVIGATION_CHAR_UUID}")
            logger.info(f"  - LN Feature: {LN_FEATURE_CHAR_UUID}")
            logger.info(f"Waiting for GPS2IP connections...")
            
        except Exception as e:
            logger.error(f"Failed to start BLE server: {e}")
            logger.info("Note: BLE server requires bluez and proper permissions.")
            logger.info("On Raspberry Pi, ensure bluetooth is enabled and user has permissions.")
            raise
    
    async def _start_bluez_server(self):
        """
        Start BLE server using bluez D-Bus API directly.
        This is a fallback when BleakServer is not available.
        """
        try:
            import dbus
            import dbus.exceptions
            import dbus.mainloop.glib
            from gi.repository import GLib
            
            logger.info("Starting bluez D-Bus GATT server...")
            # This is a placeholder - full implementation would require
            # setting up bluez GATT server via D-Bus
            # For now, we'll log that this needs to be implemented
            logger.warning("Direct bluez D-Bus implementation not yet complete.")
            logger.warning("Please install a newer version of bleak that supports BleakServer,")
            logger.warning("or use the phone app in client mode to connect to a BLE device.")
            raise NotImplementedError("Direct bluez D-Bus server not implemented. Use bleak >= 0.20.0")
            
        except ImportError:
            logger.error("dbus and gi.repository not available for bluez D-Bus API")
            raise
    
    async def stop_server(self):
        """
        Stop the BLE server and stop advertising.
        """
        if not self.is_running:
            return
        
        try:
            if self.server:
                await self.server.stop()
            self.is_running = False
            logger.info("BLE GPS Receiver stopped")
        except Exception as e:
            logger.error(f"Error stopping BLE server: {e}")
    
    def _on_connect(self, client_address: str):
        """
        Handle client connection.
        
        Args:
            client_address: MAC address of connecting device
        """
        was_connected = len(self.connected_devices) > 0
        self.connected_devices.add(client_address)
        connected_count = len(self.connected_devices)
        
        logger.info(f"GPS2IP device connected: {client_address} ({connected_count} connected)")
        
        # Call connection callback if provided
        if self.connection_callback:
            try:
                self.connection_callback('connected', client_address, connected_count)
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")
        
        # Log first connection
        if not was_connected:
            logger.info("BLE GPS receiver now has active connection(s)")
    
    def _on_disconnect(self, client_address: str):
        """
        Handle client disconnection.
        
        Args:
            client_address: MAC address of disconnecting device
        """
        was_connected = len(self.connected_devices) > 0
        
        if client_address in self.connected_devices:
            self.connected_devices.remove(client_address)
        
        connected_count = len(self.connected_devices)
        logger.info(f"GPS2IP device disconnected: {client_address} ({connected_count} connected)")
        
        # Call connection callback if provided
        if self.connection_callback:
            try:
                self.connection_callback('disconnected', client_address, connected_count)
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")
        
        # Log when all devices disconnected
        if was_connected and connected_count == 0:
            logger.info("All BLE GPS devices disconnected - still advertising for reconnection")
            logger.info("  (GPS2IP apps can reconnect automatically)")
    
    def get_latest_gps(self) -> Optional[dict]:
        """
        Get the latest received GPS data.
        
        Returns:
            Latest GPS data dict or None if no data received yet
        """
        return self.latest_gps_data
    
    def is_connected(self) -> bool:
        """
        Check if any phone is connected.
        
        Returns:
            True if at least one device is connected
        """
        return len(self.connected_devices) > 0


# Async event loop management
_ble_receiver: Optional[BLEGPSReceiver] = None
_ble_loop: Optional[asyncio.AbstractEventLoop] = None
_ble_task: Optional[asyncio.Task] = None


def start_ble_gps_receiver(gps_callback: Optional[Callable] = None, connection_callback: Optional[Callable] = None) -> bool:
    """
    Start the BLE GPS receiver in a background thread.
    
    Args:
        gps_callback: Optional callback function for GPS updates
        connection_callback: Optional callback function for connection changes
        
    Returns:
        True if started successfully, False otherwise
    """
    global _ble_receiver, _ble_loop, _ble_task
    
    try:
        # Create receiver
        _ble_receiver = BLEGPSReceiver(gps_callback=gps_callback, connection_callback=connection_callback)
        
        # Create new event loop for BLE
        _ble_loop = asyncio.new_event_loop()
        
        # Start server in the event loop
        def run_ble_server():
            _ble_loop.run_until_complete(_ble_receiver.start_server())
            _ble_loop.run_forever()
        
        # Run in background thread
        import threading
        _ble_task = threading.Thread(target=run_ble_server, daemon=True)
        _ble_task.start()
        
        logger.info("BLE GPS receiver started in background thread")
        return True
        
    except Exception as e:
        logger.error(f"Failed to start BLE GPS receiver: {e}")
        return False


def stop_ble_gps_receiver():
    """
    Stop the BLE GPS receiver.
    """
    global _ble_receiver, _ble_loop
    
    try:
        if _ble_receiver and _ble_loop:
            _ble_loop.call_soon_threadsafe(
                lambda: asyncio.create_task(_ble_receiver.stop_server())
            )
        logger.info("BLE GPS receiver stopped")
    except Exception as e:
        logger.error(f"Error stopping BLE GPS receiver: {e}")


def get_ble_gps_receiver() -> Optional[BLEGPSReceiver]:
    """
    Get the current BLE GPS receiver instance.
    
    Returns:
        BLEGPSReceiver instance or None if not started
    """
    return _ble_receiver


if __name__ == "__main__":
    # Test the BLE receiver standalone
    def test_gps_callback(gps_data: dict):
        print(f"Received GPS: {gps_data}")
    
    print("Starting BLE GPS Receiver test...")
    print("Connect a phone app to test GPS data reception")
    
    receiver = BLEGPSReceiver(gps_callback=test_gps_callback)
    
    try:
        asyncio.run(receiver.start_server())
        # Keep running
        while True:
            asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        asyncio.run(receiver.stop_server())
