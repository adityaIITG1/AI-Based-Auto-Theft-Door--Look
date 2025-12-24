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
        try:
            self.serial_conn = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset
            self.logger.info(f"Connected to Arduino on {self.port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Arduino: {e}")
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
