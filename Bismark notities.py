from pyfirmata2 import Arduino, util
import time
import signal
import sys

# ===================== CONFIG =====================
PORT = 'COM3'            # Pas aan indien nodig
THRESHOLD = 0.45         # Zwart/wit-drempel (0..1) -> kalibreren!
BASE_SPEED = 0.3
SMOOTH_TURN = 0.4
SHARP_TURN  = 0.8

NO_LINE_TIMEOUT = 4.0    # s zonder lijn -> stoppen
CROSS_COOLDOWN  = 0.8    # s na bocht geen nieuwe kruispuntbeslissing
ROLL_AFTER_SEG   = 0.5   # s kort doorrollen na segment klaar

INVERT_TURNS = False     # True als links/rechts fysiek gespiegeld is

# ===================== ROUTEPLANNING =====================
# Start bij Trein depot; pas aan als je baan anders loopt
ROUTES = {
    "depot-achtbaan":     {"plan": ["rechtdoor, rechtdoor, rechtdoor, rechtdoor, links, rechtdoor"],  "loc": "Trein depot"},
}
ROUTE_VOLGORDE = [
    "depot-achtbaan"
]

# ===================== ARDUINO =====================
board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1.0)

def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

# ---- SENSOREN (A1..A5) ----
# sensor_values in volgorde: [R1, R2, M, L2, L1]
sensor_values = [0.5, 0.5, 0.5, 0.5, 0.5]

def maak_callback(index):
    def callback(data):
        sensor_values[index] = 0.5 if data is None else float(data)
    return callback

raw_sensors = [
    board.get_pin('a:1:i'),  # R1 (buiten rechts)
    board.get_pin('a:2:i'),  # R2
    board.get_pin('a:3:i'),  # M
    board.get_pin('a:4:i'),  # L2
    board.get_pin('a:5:i'),  # L1 (buiten links)
]
for i, s in enumerate(raw_sensors):
    s = require_pin(s, f"sensor A{i+1}")
    s.register_callback(maak_callback(i))
    s.enable_reporting()
time.sleep(1.0)

def bin_pattern():
    """Analoog -> binair (1=zwart, 0=wit); return (L1,L2,M,R2,R1)."""
    R1 = 1 if sensor_values[0] < THRESHOLD else 0
    R2 = 1 if sensor_values[1] < THRESHOLD else 0
    M  = 1 if sensor_values[2] < THRESHOLD else 0
    L2 = 1 if sensor_values[3] < THRESHOLD else 0
    L1 = 1 if sensor_values[4] < THRESHOLD else 0
    return (L1, L2, M, R2, R1)

def has_line():
    return any(v < THRESHOLD for v in sensor_values)

# ---- MOTORPINNEN (jouw layout) ----
motor_links     = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links  = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links     = require_pin(board.get_pin('d:8:o'),  "brake_links D8")

motor_rechts    = require_pin(board.get_pin('d:3:p'),  "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts    = require_pin(board.get_pin('d:9:o'),  "brake_rechts D9")

# (optioneel) Ultrasoon – pins alvast klaar, niet gebruikt hier
echo_pin = require_pin(board.get_pin('d:6:o'), "ultrasonic trig D6")
trig_pin = require_pin(board.get_pin('d:7:i'), "ultrasonic echo D7")

# ===================== MOTORCONTROLLER =====================
def clamp01(x): 
    return max(0.0, min(1.0, float(x)))

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
        left = clamp01(left); right = clamp01(right)
        self.richting_links.write(0)   # vooruit
        self.richting_rechts.write(0)  # vooruit
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def forward(self, speed=BASE_SPEED):
        self.set_speeds(speed, speed)

    def backward(self, speed=BASE_SPEED):
        self.richting_links.write(1); self.richting_rechts.write(1)
        self.motor_links.write(clamp01(speed))
        self.motor_rechts.write(clamp01(speed))

    def draaien(self, speed=BASE_SPEED):        # rechtsom spin
        self.richting_links.write(0); self.richting_rechts.write(1)
        self.motor_links.write(clamp01(speed)); self.motor_rechts.write(clamp01(speed))

    def draaien_tegen(self, speed=BASE_SPEED):  # linksom spin
        self.richting_links.write(1); self.richting_rechts.write(0)
        self.motor_links.write(clamp01(speed)); self.motor_rechts.write(clamp01(speed))

    def stop(self):
        self.motor_links.write(0)
        self.motor_rechts.write(0)

# ===================== LIJNVOLGER + ROUTE =====================
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "rechtdoor"
        self.last_turn_time = 0.0

        # route state
        self.route_index = 0
        self.route_key = ROUTE_VOLGORDE[self.route_index]
        self.route_plan = ROUTES[self.route_key]["plan"]
        self.route_max  = len(self.route_plan)
        self.route_step = 0

        self.no_line_elapsed = 0.0

    def choose(self, direction, base=BASE_SPEED):
        dir_eff = direction
        if INVERT_TURNS:
            if dir_eff == "links": dir_eff = "rechts"
            elif dir_eff == "rechts": dir_eff = "links"

        if direction == "links":
            print("links")
            self.mc.set_speeds(base*(1-SHARP_TURN), base*(1+SHARP_TURN))
        elif direction == "rechts":
            print("rechts")
            self.mc.set_speeds(base*(1+SHARP_TURN), base*(1-SHARP_TURN))
        else:
            print("rechtdoor")
            self.mc.forward(base)

        self.last_direction = direction
        self.last_turn_time = time.time()

    def handle_crossings(self):
        if self.route_step >= self.route_max:
            return False
        if time.time() - self.last_turn_time < CROSS_COOLDOWN:
            return False

        L1, L2, M, R2, R1 = bin_pattern()
        cross_left  = bool(M and L1 and L2)
        cross_right = bool(M and R1 and R2)
        cross_all   = bool(L1 and L2 and M and R2 and R1)

        if cross_left or cross_right or cross_all:
            next_dir = self.route_plan[self.route_step]  # 'links'/'rechts'/'rechtdoor'
            self.choose(next_dir)
            self.route_step += 1
            return True
        return False

    def steer_on_line(self):
        L1, L2, M, R2, R1 = bin_pattern()

        if L1 and not (L2 or M or R2 or R1):
            print("links")
            self.mc.set_speeds(0, BASE_SPEED); return

        if L2 and not (M or R2 or R1):
            print("links")
            self.mc.set_speeds(BASE_SPEED*0.40, BASE_SPEED); return

        if R1 and not (R2 or M or L2 or L1):
            print("rechts")
            self.mc.set_speeds(BASE_SPEED, 0); return

        if R2 and not (M or L2 or L1):
            print("rechts")
            self.mc.set_speeds(BASE_SPEED, BASE_SPEED*0.40); return

        if M:
            print("rechtdoor")
            self.mc.forward(BASE_SPEED); return

        print("lijn kwijt")
        self.mc.forward(BASE_SPEED * 0.4)

    def segment_done(self):
        return self.route_step >= self.route_max and not has_line()

    def load_next_route(self):
        self.route_index += 1
        if self.route_index >= len(ROUTE_VOLGORDE):
            return False
        self.route_key  = ROUTE_VOLGORDE[self.route_index]
        self.route_plan = ROUTES[self.route_key]["plan"]
        self.route_max  = len(self.route_plan)
        self.route_step = 0
        return True

    def loop(self):
        time.sleep(0.1)

        if has_line():
            self.no_line_elapsed = 0.0
            if not self.handle_crossings():
                self.steer_on_line()
        else:
            self.no_line_elapsed += 0.1
            if self.no_line_elapsed >= NO_LINE_TIMEOUT:
                print("lijn kwijt")
                self.mc.stop()

        if self.segment_done():
            # kleine uitrol
            self.mc.forward(BASE_SPEED)
            time.sleep(ROLL_AFTER_SEG)
            self.mc.stop()

            # volgende route of klaar
            if not self.load_next_route():
                return False

            # draai tot lijn weer gevonden is
            self.mc.draaien(BASE_SPEED)
            while not has_line():
                time.sleep(0.1)
            self.mc.stop()
            time.sleep(0.3)

        return True

# ===================== INSTANTIES =====================
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts
)
lijnvolger = LineFollower(motor_controller)

# ===================== NETTE EXIT =====================
def signal_handler(sig, frame):
    try:
        motor_controller.stop()
    finally:
        board.exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ===================== MAIN =====================
print("Start lijnvolgen... (Ctrl+C om te stoppen)")
time.sleep(1.0)

try:
    while True:
        if not lijnvolger.loop():
            break
except KeyboardInterrupt:
    pass
finally:
    motor_controller.stop()
    board.exit()
    print("Programma gestopt.")