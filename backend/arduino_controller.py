import serial
import time
import logging

class ArduinoController:
    def __init__(self, port='COM3', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.serial_conn = None
        self.logger = logging.getLogger("Arduino")

    def connect(self):
        # Try the specified port first
        if self._try_port(self.port):
            return True
        
        # If default fails, scan for available ports
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        self.logger.info(f"Scanning {len(ports)} ports for Arduino...")
        
        for p in ports:
            if p.device == self.port: continue # Already tried
            if self._try_port(p.device):
                self.port = p.device
                return True
                
        return False

    def _try_port(self, port_name):
        try:
            self.logger.info(f"Attempting to connect on {port_name}...")
            self.serial_conn = serial.Serial(port_name, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            self.logger.info(f"[SUCCESS] Connected to Arduino on {port_name}")
            return True
        except Exception as e:
            self.logger.debug(f"Port {port_name} failed: {e}")
            return False

    def send_command(self, command):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(f"{command}\n".encode())
                self.logger.info(f"Sent command: {command}")
            except Exception as e:
                self.logger.error(f"Failed to send command: {e}")
        else:
            self.logger.warning("Arduino not connected, command skipped.")

    def lock_door(self):
        self.send_command("LOCK")

    def unlock_door(self):
        self.send_command("UNLOCK")
    
    def warning_siren(self):
        self.send_command("WARN")

    def silence_siren(self):
        self.send_command("SILENCE")

    def read_status(self):
        """Read lines from Serial and return meaningful status updates."""
        if self.serial_conn and self.serial_conn.is_open and self.serial_conn.in_waiting > 0:
            try:
                line = self.serial_conn.readline().decode().strip()
                if line:
                    return line
            except Exception:
                pass
        return None
