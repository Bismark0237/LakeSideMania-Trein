from pyfirmata2 import Arduino, util
import time
import signal
import sys

# === CONFIGURATIE ===
PORT = 'COM3'          # Pas aan indien nodig
BASE_SPEED = 0.3
THRESHOLD = 0.5        # drempel voor zwart/wit
Kp = 0.4               # gevoeligheid voor bijsturen
ALPHA = 0.3            # demping voor vloeiender motorreactie

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
sensor_values = [0.5, 0.5, 0.5, 0.5, 0.5]  # neutraal starten

def maak_callback(index):
    def callback(data):
        sensor_values[index] = data if data is not None else 0.5
    return callback

raw_sensors = [
    board.get_pin('a:0:i'),
    board.get_pin('a:1:i'),
    board.get_pin('a:2:i'),
    board.get_pin('a:3:i'),
    board.get_pin('a:4:i')
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
        # Remmen los
        self.brake_links.write(0)
        self.brake_rechts.write(0)

        # Limiteer waarden
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def stop(self):
        self.motor_links.write(0)
        self.motor_rechts.write(0)
        # rem kort in
        self.brake_links.write(1)
        self.brake_rechts.write(1)

# === LIJNVOLGERSYSTEEM ===
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"
        self.prev_left = BASE_SPEED
        self.prev_right = BASE_SPEED

    def read_sensors(self):
        # Binariseer op basis van drempelwaarde
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        return pattern

    def navigate_pid(self):
        """
        PID-achtige bijsturing met gewichten per sensor.
        Dit maakt bochten vloeiender.
        """
        weights = [-2, -1, 0, 1, 2]
        weighted_sum = 0
        total_active = 0
        for i, val in enumerate(sensor_values):
            if val < THRESHOLD:
                weighted_sum += weights[i]
                total_active += 1

        if total_active == 0:
            error = 0
        else:
            error = weighted_sum / total_active

        correction = Kp * error
        left_speed = BASE_SPEED - correction
        right_speed = BASE_SPEED + correction

        # Demping voor vloeiender resultaat
        self.prev_left = (1 - ALPHA) * self.prev_left + ALPHA * left_speed
        self.prev_right = (1 - ALPHA) * self.prev_right + ALPHA * right_speed

        # Beperk snelheden
        self.prev_left = max(0, min(1, self.prev_left))
        self.prev_right = max(0, min(1, self.prev_right))

        self.mc.set_speeds(self.prev_left, self.prev_right)

        # Richting onthouden
        if correction < -0.05:
            self.last_direction = "left"
        elif correction > 0.05:
            self.last_direction = "right"
        else:
            self.last_direction = "straight"

    def follow_line(self):
        pattern = self.read_sensors()
        print(f"Sens: {pattern}")

        # === Kruispunt detectie ===
        if all(pattern):
            print("Kruispunt → rechtdoor")
            self.mc.set_speeds(BASE_SPEED, BASE_SPEED)
            self.last_direction = "straight"
            return

        # === Geen lijn gevonden → herstelstrategie ===
        if pattern == [0, 0, 0, 0, 0]:
            print("Lijn kwijt → zoeken...")
            self.mc.stop()
            time.sleep(0.1)

            if self.last_direction == "left":
                # Draai iets naar links om lijn te zoeken
                self.mc.set_speeds(0.2, 0.6)
            elif self.last_direction == "right":
                # Draai iets naar rechts
                self.mc.set_speeds(0.6, 0.2)
            else:
                # Geen richting bekend → langzaam rechtdoor
                self.mc.set_speeds(0.4, 0.4)
            return

        # === Normaal lijnvolgen ===
        self.navigate_pid()

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
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    motor_controller.stop()
    board.exit()
    print("Programma gestopt.")