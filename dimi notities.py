"""
LINE FOLLOWER ROBOT – ROUTE SYSTEM + STABIELE LINIEVOLGER (GECOMBINEERD)
"""

from pyfirmata2 import Arduino, util
import time
import signal
import sys

# ================================================================
# CONFIGURATIE
# ================================================================

ARDUINO_PORT = 'COM3'

BASE_SPEED = 0.2
SMOOTH_TURN = 0.5
SHARP_TURN = 0.8
THRESHOLD = 0.5

CROSS_COOLDOWN = 0.5
POST_TURN_DELAY = 0.4

ROUTES = {
    "depot-arcade": ["right", "left", "stop"],
    "depot-wildwaterbaan": ["right", "straight", "straight", "left", "left", "stop"],
    "depot-achtbaan": ["straight", "straight", "straight", "left", "stop"]
}

ROUTE_SEQUENCE = "depot-arcade"

# ================================================================
# ARDUINO INIT
# ================================================================

def init_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' niet gevonden.")
    return pin

def setup_board():
    board = Arduino(ARDUINO_PORT)
    it = util.Iterator(board)
    it.start()
    time.sleep(1)
    return board

def setup_sensors(board):
    sensor_vals = [0.5] * 5

    def make_cb(i):
        def cb(data):
            if data is not None:
                sensor_vals[i] = data
        return cb

    pins = [board.get_pin(f'a:{i}:i') for i in range(1, 6)]
    for i, p in enumerate(pins):
        p = init_pin(p, f"sensor A{i+1}")
        p.register_callback(make_cb(i))
        p.enable_reporting()

    time.sleep(1)
    return sensor_vals

def setup_motors(board):
    config = {
        "left": {
            "pwm": init_pin(board.get_pin('d:11:p'), "left PWM"),
            "dir": init_pin(board.get_pin('d:13:o'), "left DIR"),
            "brk": init_pin(board.get_pin('d:8:o'),  "left BRK")
        },
        "right": {
            "pwm": init_pin(board.get_pin('d:3:p'), "right PWM"),
            "dir": init_pin(board.get_pin('d:12:o'), "right DIR"),
            "brk": init_pin(board.get_pin('d:9:o'),  "right BRK")
        }
    }
    return config

# ================================================================
# MOTORCONTROLLER
# ================================================================

class MotorController:
    def __init__(self, cfg):
        self.l = cfg["left"]
        self.r = cfg["right"]

        self.l["dir"].write(0)
        self.r["dir"].write(0)
        self.l["brk"].write(0)
        self.r["brk"].write(0)

    def set(self, left, right):
        left = max(0, min(1, float(left)))
        right = max(0, min(1, float(right)))
        self.l["pwm"].write(left)
        self.r["pwm"].write(right)

    def forward(self, s=BASE_SPEED):
        self.l["dir"].write(0)
        self.r["dir"].write(0)
        self.set(s, s)

    def backward(self, s=BASE_SPEED):
        self.l["dir"].write(1)
        self.r["dir"].write(1)
        self.set(s, s)

    def turn_left(self, s=0.25):
        self.l["dir"].write(1)
        self.r["dir"].write(0)
        self.set(s, s)

    def turn_right(self, s=0.25):
        self.l["dir"].write(0)
        self.r["dir"].write(1)
        self.set(s, s)

    def stop(self):
        self.set(0, 0)

# ================================================================
# GECOMBINEERDE LIJN + ROUTE LOGICA
# ================================================================

class LineFollower:
    def __init__(self, motor, sensors, route_key):
        self.m = motor
        self.sensors = sensors
        self.route = ROUTES[route_key]
        self.route_step = 0
        self.last_turn_time = 0
        self.last_dir = "straight"

    # ---------- SENSORLEZEN ----------
    def read(self):
        pattern = [1 if v < THRESHOLD else 0 for v in self.sensors]
        return pattern

    # ---------- ROUTE TURN ----------
    def do_turn(self, act):
        print(f"\n>>> ROUTE TURN: {act}")

        if act == "left":
            self.m.forward()
            time.sleep(0.20)
            self.m.stop()
            time.sleep(0.25)
            self.m.turn_left(0.3)
            time.sleep(0.55)
            self.m.stop()

        elif act == "right":
            self.m.forward()
            time.sleep(0.20)
            self.m.stop()
            time.sleep(0.25)
            self.m.turn_right(0.3)
            time.sleep(0.55)
            self.m.stop()

        elif act == "straight":
            self.m.forward(BASE_SPEED)
            time.sleep(0.35)

        elif act == "stop":
            print(">>> EINDBESTEMMING")
            self.m.forward()
            time.sleep(1)
            self.m.stop()
            sys.exit(0)

        time.sleep(POST_TURN_DELAY)

    def detect_junction(self, p):
        lo, li, m, ri, ro = p
        left_j = lo == 1 and (li == 1 or m == 1)
        right_j = ro == 1 and (ri == 1 or m == 1)
        cross = lo == 1 and ro == 1
        return left_j or right_j or cross

    # ---------- ROUTE HANDLER ----------
    def route_handler(self):
        if self.route_step >= len(self.route):
            return False

        if time.time() - self.last_turn_time < CROSS_COOLDOWN:
            return False

        p = self.read()

        if self.detect_junction(p):
            act = self.route[self.route_step]
            self.do_turn(act)
            self.last_turn_time = time.time()
            self.route_step += 1
            return True
        return False

    # ---------- LINE FOLLOW LOGICA (VAN JOUW OUDE CODE) ----------
    def follow_line(self):
        L1, L2, M, R2, R1 = self.read()
        pattern = [L1, L2, M, R2, R1]
        print("Sensors:", pattern)

        # Rechtdoor
        if pattern in ([0,0,1,0,0], [0,1,1,1,0], [0,1,1,0,0], [0,0,1,1,0]):
            print("→ Rechtdoor")
            self.m.forward(BASE_SPEED)
            self.last_dir = "straight"
            return

        # Links
        if pattern in ([1,0,0,0,0], [1,1,0,0,0]):
            print("→ Link scherp")
            self.m.set(BASE_SPEED*(1-SHARP_TURN*1.5),
                       BASE_SPEED*(1+SHARP_TURN))
            self.last_dir = "left"
            return

        if pattern in ([0,1,0,0,0], [0,1,1,0,0]):
            print("→ Link bocht")
            self.m.set(BASE_SPEED*(1-SMOOTH_TURN*1.5),
                       BASE_SPEED*(1+SMOOTH_TURN))
            self.last_dir = "left"
            return

        # Rechts
        if pattern in ([0,0,0,0,1], [0,0,0,1,1]):
            print("→ Rechts scherp")
            self.m.set(BASE_SPEED*(1+SHARP_TURN),
                       BASE_SPEED*(1-SHARP_TURN*1.5))
            self.last_dir = "right"
            return

        if pattern in ([0,0,0,1,0], [0,0,1,1,0]):
            print("→ Rechts bocht")
            self.m.set(BASE_SPEED*(1+SMOOTH_TURN),
                       BASE_SPEED*(1-SMOOTH_TURN*1.5))
            self.last_dir = "right"
            return

        # Kruispunt
        if pattern == [1,1,1,1,1]:
            print("→ Kruispunt detectie (line follow)")
            self.m.forward(BASE_SPEED)
            return

        # Lijn kwijt
        if pattern == [0,0,0,0,0]:
            print("!!! Lijn kwijt !!!")
            self.m.backward(BASE_SPEED*0.4)
            time.sleep(0.25)
            self.m.stop()

            if self.last_dir == "left":
                print("Herstel → links zoeken")
                self.m.turn_left(0.3)
                time.sleep(0.25)
            elif self.last_dir == "right":
                print("Herstel → rechts zoeken")
                self.m.turn_right(0.3)
                time.sleep(0.25)

            print("Vooruit zoeken…")
            self.m.forward(BASE_SPEED*0.4)
            time.sleep(0.35)
            return

        print("→ Onbekend patroon → langzaam vooruit")
        self.m.forward(BASE_SPEED*0.8)

    # ---------- MAIN UPDATE ----------
    def update(self):
        if not self.route_handler():
            self.follow_line()

# ================================================================
# MAIN PROGRAMMA
# ================================================================

def graceful_exit(m, board):
    def h(sig, frame):
        print("Stoppen…")
        m.stop()
        board.exit()
        sys.exit(0)
    signal.signal(signal.SIGINT, h)

def main():
    board = setup_board()
    sensors = setup_sensors(board)
    motors = setup_motors(board)

    mc = MotorController(motors)
    lf = LineFollower(mc, sensors, ROUTE_SEQUENCE)

    graceful_exit(mc, board)

    print("\n=== ROBOT GESTART – ROUTE NAAR:", ROUTE_SEQUENCE, "===\n")
    time.sleep(2)

    while True:
        lf.update()
        time.sleep(0.02)

if __name__ == "__main__":
    main()