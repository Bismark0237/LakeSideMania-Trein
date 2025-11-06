from pyfirmata2 import Arduino, util
import time
import signal
import sys

# ==============================
# Configuratie
# ==============================
PORT = 'COM3'          # Pas aan indien nodig

BASE_SPEED_LEFT = 0.27     # linker motor basis
BASE_SPEED_RIGHT = 0.31    # rechter motor basis

SHARP_TURN = 0.8
SMOOTH_TURN = 0.4
THRESHOLD = 0.5        # drempel voor zwart/wit

# ==============================
# Setup Arduino & sensoren
# ==============================
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1)

sensor_values = [0.5, 0.5, 0.5, 0.5, 0.5]

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

for i, s in enumerate(raw_sensors):
    s = require_pin(s, f"sensor A{i}")
    s.register_callback(maak_callback(i))
    s.enable_reporting()

time.sleep(1)

# ==============================
# Motorpinnen
# ==============================
motor_links = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links = require_pin(board.get_pin('d:8:o'), "brake_links D8")

motor_rechts = require_pin(board.get_pin('d:3:p'), "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts = require_pin(board.get_pin('d:9:o'), "brake_rechts D9")

time.sleep(1)

# ==============================
# Motorcontroller (differentiële besturing)
# ==============================
class MotorController:
    def __init__(self, motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts,
                 base_left=BASE_SPEED_LEFT, base_right=BASE_SPEED_RIGHT):
        self.motor_links = motor_links
        self.motor_rechts = motor_rechts
        self.richting_links = richting_links
        self.richting_rechts = richting_rechts
        self.brake_links = brake_links
        self.brake_rechts = brake_rechts

        self.base_left = float(base_left)
        self.base_right = float(base_right)

        # vooruit, remmen uit
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.brake_links.write(0)
        self.brake_rechts.write(0)

    def set_speeds(self, left, right):
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def set_scaled(self, left_scale, right_scale):
        self.set_speeds(self.base_left * left_scale,
                        self.base_right * right_scale)

    def forward(self, scale=1.0):
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.set_scaled(scale, scale)

    def draaien(self, scale=0.8):
        """Rechtsom draaien door links trager, rechts sneller."""
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.motor_links.write(0.3)
        self.motor_rechts.write(0)

    def draaien_tegen(self, scale=0.8):
        """Linksom draaien door links sneller, rechts trager."""
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.motor_links.write(0)
        self.motor_rechts.write(0.3)

    def stop(self):
        self.set_speeds(0, 0)

# ==============================
# Lijnvolger
# ==============================
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"

    def read_sensors(self):
        """Lees sensoren en geef binaire 0/1 waarden."""
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        return pattern

    def spin_until_center(self, direction, scale=0.8, timeout=2.5):
        """Blijf draaien tot middenpatroon gevonden of timeout."""
        start = time.time()
        if direction == "left":
            self.mc.draaien_tegen(scale)
        else:
            self.mc.draaien(scale)

        while time.time() - start < timeout:
            pattern = self.read_sensors()
            if pattern in ([0,0,1,0,0], [0,1,1,0,0], [0,0,1,1,0], [0,1,1,1,0]):
                self.mc.stop()
                return True
            if direction == "left":
                self.mc.draaien_tegen(scale)
            else:
                self.mc.draaien(scale)
            time.sleep(0.01)

        self.mc.stop()
        return False

    def follow_line(self):
        L1, L2, M, R2, R1 = self.read_sensors()
        pattern = [L1, L2, M, R2, R1]
        print(f"Sens: {pattern}")

        # Rechtdoor
        if pattern in ([0,0,1,0,0], [0,1,1,1,0], [0,0,1,1,0], [0,1,1,0,0], [0,1,0,1,0]):
            print("Rechtdoor")
            self.mc.forward(1.0)
            self.last_direction = "straight"

        # Kruispunt (alles zwart)
        elif pattern == [1,1,1,1,1]:
            print("Kruispunt → rechtdoor")
            self.mc.forward(1.0)
            self.last_direction = "straight"

        # Linker T-splitsing
        elif pattern == [1,1,1,0,0]:
            print("Linker T-splitsing → draai links tot midden")
            ok = self.spin_until_center(direction="left", scale=0.8, timeout=2.0)
            if ok:
                self.mc.forward(1.0)
            self.last_direction = "left"

        # Rechter T-splitsing
        elif pattern == [0,0,1,1,1]:
            print("Rechter T-splitsing → draai rechts tot midden")
            ok = self.spin_until_center(direction="right", scale=0.8, timeout=2.0)
            if ok:
                self.mc.forward(1.0)
            self.last_direction = "right"

        # Correctie links
        elif pattern in ([0,1,0,0,0], [1,1,0,0,0], [1,0,0,0,0]):
            print("Correctie naar links")
            self.mc.set_scaled(SMOOTH_TURN, 1.0)
            self.last_direction = "left"

        # Correctie rechts
        elif pattern in ([0,0,0,1,0], [0,0,1,1,0], [0,0,0,0,1]):
            print("Correctie naar rechts")
            self.mc.set_scaled(1.0, SMOOTH_TURN)
            self.last_direction = "right"

        # Lijn verloren
        else:
            print("Lijn verloren! Herstelpoging...")
            self.mc.stop()
            ok = self.spin_until_center(direction=self.last_direction, scale=0.8, timeout=2.5)
            if not ok:
                # probeer de andere kant ook even
                other = "left" if self.last_direction == "right" else "right"
                self.spin_until_center(direction=other, scale=0.8, timeout=2.5)

# ==============================
# Setup en main loop
# ==============================
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts,
    base_left=BASE_SPEED_LEFT,
    base_right=BASE_SPEED_RIGHT
)
lijnvolger = LineFollower(motor_controller)

def signal_handler(sig, frame):
    print("\nStoppen...")
    motor_controller.stop()
    board.exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

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