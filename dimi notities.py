from pyfirmata2 import Arduino, util
import time
import signal
import sys

# === CONFIGURATIE ===
PORT = 'COM3'          # Pas aan indien nodig
BASE_SPEED = 0.8
SHARP_TURN = 0.8
SMOOTH_TURN = 0.3
THRESHOLD = 0.5        # drempel voor zwart/wit

# === HULP: pin-checker ===
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

# === ARDUINO VERBINDING ===
board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1)

# === SENSORPINNEN (5-KANAALS LIJNSENSOR) ===
sensor_values = [0.5, 0.5, 0.5, 0.5, 0.5]  # start met neutrale waardes

def maak_callback(index):
    def callback(data):
        sensor_values[index] = data if data is not None else 0.5
    return callback

raw_sensors = [
    board.get_pin('a:1:i'),
    board.get_pin('a:2:i'),
    board.get_pin('a:3:i'),
    board.get_pin('a:4:i'),
    board.get_pin('a:5:i')
]

# Enable reporting + callbacks
for i, s in enumerate(raw_sensors):
    s = require_pin(s, f"sensor A{i}")
    s.register_callback(maak_callback(i))
    s.enable_reporting()

time.sleep(1)

# === MOTORPINNEN ===
motor_links = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links = require_pin(board.get_pin('d:8:o'), "brake_links D8")

motor_rechts = require_pin(board.get_pin('d:3:p'), "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts = require_pin(board.get_pin('d:9:o'), "brake_rechts D9")

time.sleep(1)

# === MOTORCONTROLLER ===
class MotorController:
    def __init__(self, motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts):
        self.motor_links = motor_links
        self.motor_rechts = motor_rechts
        self.richting_links = richting_links
        self.richting_rechts = richting_rechts
        self.brake_links = brake_links
        self.brake_rechts = brake_rechts

        # standaard: vooruit, remmen uit
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.brake_links.write(0)
        self.brake_rechts.write(0)

    def set_speeds(self, left, right):
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def forward(self, speed=BASE_SPEED):
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.motor_links.write(speed)
        self.motor_rechts.write(speed)

    def backward(self, speed=BASE_SPEED):
        self.richting_links.write(1)
        self.richting_rechts.write(1)
        self.motor_links.write(speed)
        self.motor_rechts.write(speed)

    def stop(self):
        self.motor_links.write(0)
        self.motor_rechts.write(0)

# === LIJNVOLGERSYSTEEM ===
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"

    def read_sensors(self):
        """Leest de waarden van de globale sensor_values en vertaalt ze naar 0/1."""
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        return pattern

    def navigate_turn(self, direction, sharpness):
        """Bochtnavigatie"""
        if direction == "left":
            self.mc.set_speeds(BASE_SPEED * (1 - sharpness),
                               BASE_SPEED * (1 + sharpness))
        elif direction == "right":
            self.mc.set_speeds(BASE_SPEED * (1 + sharpness),
                               BASE_SPEED * (1 - sharpness))

    def follow_line(self):
        L1, L2, M, R2, R1 = self.read_sensors()
        pattern = [L1, L2, M, R2, R1]
        print(f"Sens: {pattern}")

        # --- RECHTDOOR ---
        if pattern in ([0,0,1,0,0], [0,1,1,1,0], [0,0,1,1,0], [0,1,1,0,0], [0,1,0,1,0]):
            print("Rechtdoor")
            self.mc.forward(BASE_SPEED)
            self.last_direction = "straight"

        # --- LINKS ---
        elif pattern in ([0,1,1,0,0], [1,1,0,0,0], [1,1,1,0,0], [1,0,0,0,0], [1,0,1,0,0]):
            print("Links bocht")
            self.navigate_turn("left", SMOOTH_TURN)
            self.last_direction = "left"

        elif pattern in ([1,1,1,1,0], [1,1,0,1,0], [1,1,1,0,1]):
            print("Links scherp")
            self.navigate_turn("left", SHARP_TURN)
            self.last_direction = "left"

        # --- RECHTS ---
        elif pattern in ([0,0,1,1,0], [0,0,0,1,1], [0,0,0,0,1], [0,1,0,0,1], [0,0,1,0,1]):
            print("Rechts bocht")
            self.navigate_turn("right", SMOOTH_TURN)
            self.last_direction = "right"

        elif pattern in ([0,1,1,1,1], [0,0,1,1,1], [1,0,1,1,1]):
            print("Rechts scherp")
            self.navigate_turn("right", SHARP_TURN)
            self.last_direction = "right"

        # --- KRUISPUNT ---
        elif pattern == [1,1,1,1,1]:
            print("Kruispunt gedetecteerd → rechtdoor")
            self.mc.forward(BASE_SPEED)
            self.last_direction = "straight"

        # --- LIJN VERLOREN ---
        elif pattern == [0,0,0,0,0]:
            print("Lijn verloren!")
            self.mc.backward(BASE_SPEED * 0.6)
            time.sleep(0.4)
            if self.last_direction == "left":
                print("Herstel naar links")
                self.navigate_turn("left", SHARP_TURN)
            elif self.last_direction == "right":
                print("Herstel naar rechts")
                self.navigate_turn("right", SHARP_TURN)
            else:
                print("Geen richting bekend → kort achteruit")
                self.mc.backward(BASE_SPEED * 0.5)
            time.sleep(0.4)

        # --- ONBEKENDE COMBINATIE ---
        else:
            print("Onbekend patroon → langzaam rechtdoor")
            self.mc.set_speeds(BASE_SPEED * 0.7, BASE_SPEED * 0.7)


# === INSTANTIES ===
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts
)
lijnvolger = LineFollower(motor_controller)

# === SIGNAL HANDLER ===
def signal_handler(sig, frame):
    print("\nStoppen...")
    try:
        motor_controller.stop()
    finally:
        board.exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# === MAIN LOOP ===
print("Start lijnvolgen... (Ctrl+C om te stoppen)")
time.sleep(2)

try:
    while True:
        lijnvolger.follow_line()
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    motor_controller.stop()
    board.exit()
    print("Programma gestopt.")