import serial
import time
import threading

# Configuration
SERIAL_PORT = "COM3" # Adjust as needed or make dynamic
BAUD_RATE = 9600

class HardwareController:
    def __init__(self):
        self.ser = None
        self.connected = False
        self._connect()

    def _connect(self):
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2) # Wait for Arduino reset
            self.connected = True
            print(f"[HARDWARE] Connected to Arduino on {SERIAL_PORT}")
        except Exception as e:
            print(f"[HARDWARE] Failed to connect to {SERIAL_PORT}: {e}")
            print("[HARDWARE] Running in MOCK mode.")
            self.connected = False

    def send_command(self, cmd: str):
        if self.connected and self.ser:
            try:
                self.ser.write((cmd + "\n").encode())
                print(f"[HARDWARE>>] Sent: {cmd}")
            except Exception as e:
                print(f"[HARDWARE] Error sending command: {e}")
        else:
            print(f"[MOCK-HARDWARE] Simulated Command: {cmd}")

    def lock(self):
        self.send_command("LOCK")

    def unlock(self):
        self.send_command("UNLOCK")

    def siren_on(self):
        self.send_command("SIREN_ON")

    def siren_off(self):
        self.send_command("SIREN_OFF")

# Global Instance
monitor = HardwareController()
