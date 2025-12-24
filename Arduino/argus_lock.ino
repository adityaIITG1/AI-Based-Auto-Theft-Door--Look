/*
  ARGUS - Auto Theft Door Lock System
  Target: Arduino UNO

  Connections:
  - Traffic Light Green:  Pin 5
  - Traffic Light Yellow: Pin 6 (Siren/Warning)
  - Traffic Light Red:    Pin 7
  - Relay Module (Lock):  Pin A5
  - Manual Button:        Pin 2
*/

// --- PINS ---
const int PIN_LED_GREEN = 5;
const int PIN_SIREN = 6; // Yellow LED + Buzzer
const int PIN_LED_RED = 7;
const int PIN_RELAY = A5; // Active HIGH to Lock
const int PIN_BUTTON = 2; // Push button to Ground

// --- CONFIG ---
const unsigned long LOCK_DURATION = 15000; // 15 Seconds Auto-Unlock

// --- STATE ---
bool isLocked = false;
unsigned long lockStartTime = 0;

void setup() {
  Serial.begin(9600);

  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_SIREN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  // Initial State: Unlocked
  unlockDoor();

  Serial.println("ARGUS_HARDWARE_READY");
}

void loop() {
  // 1. Check Serial Commands
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "LOCK") {
      lockDoor();
    } else if (command == "UNLOCK") {
      unlockDoor();
    } else if (command == "WARN") {
      triggerSiren();
    } else if (command == "SILENCE") {
      digitalWrite(PIN_SIREN, LOW);
    }
  }

  // 2. Check Manual Button
  if (digitalRead(PIN_BUTTON) == LOW) {
    unlockDoor();
    delay(500); // Debounce
  }

  // 3. Auto-Unlock Timer
  if (isLocked) {
    if (millis() - lockStartTime >= LOCK_DURATION) {
      unlockDoor();
    }
  }
}

void lockDoor() {
  if (!isLocked) {
    digitalWrite(PIN_RELAY, HIGH); // Activate Lock

    // Status: Red ON, Green OFF, Siren ON
    digitalWrite(PIN_LED_RED, HIGH);
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_SIREN, HIGH);

    isLocked = true;
    lockStartTime = millis();
    Serial.println("STATUS_LOCKED");
  }
}

void unlockDoor() {
  digitalWrite(PIN_RELAY, LOW); // Deactivate Lock

  // Status: Green ON, Red OFF, Siren OFF
  digitalWrite(PIN_LED_GREEN, HIGH);
  digitalWrite(PIN_LED_RED, LOW);
  digitalWrite(PIN_SIREN, LOW);

  isLocked = false;
  Serial.println("STATUS_UNLOCKED");
}

void triggerSiren() {
  // Pulse Siren/Yellow Light
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_SIREN, HIGH);
    delay(200);
    digitalWrite(PIN_SIREN, LOW);
    delay(200);
  }

  // Restore State
  if (isLocked) {
    digitalWrite(PIN_SIREN, HIGH);
  }
}
