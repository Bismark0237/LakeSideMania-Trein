from pyfirmata2 import Arduino, util
import time
import signal
import sys

# ==========================
# Configuratie
# ==========================
PORT = 'COM3'  # Pas aan indien nodig

# Aparte basis-snelheden per motor (calibreer deze!)
BASE_SPEED_LEFT  = 0.21     # linker motor basis
BASE_SPEED_RIGHT = 0.25     # rechter motor basis

# Minimale bruikbare PWM boven de dode zone (per motor)
MIN_PWM_LEFT  = 0.14
MIN_PWM_RIGHT = 0.14

# Schaalwaarden
SHARP_TURN  = 0.9   # agressiever gemaakt
SMOOTH_TURN = 0.55  # milde correcties

# Overige parameters
THRESHOLD       = 0.5   # drempel voor zwart/wit (analoge -> binair)
CROSS_COOLDOWN  = 0.5   # s na bocht geen nieuwe kruispuntbeslissing
MAIN_LOOP_SLEEP = 0.03  # snellere feedback
SELFTEST        = False  # voert een korte pivot-test uit bij start

# Routeplan
ROUTES = {
    "depot-achtbaan": {"plan": ["straight", "straight", "straight", "straight", "left", "straight"], "loc": "Trein depot"},
}
ROUTE_VOLGORDE = ["depot-achtbaan"]

# ==========================
# Hulpfuncties
# ==========================
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

# ==========================
# Arduino setup
# ==========================
board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1)

# Sensoren
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
    s = require_pin(s, f"sensor A{i+1}")
    s.register_callback(maak_callback(i))
    s.enable_reporting()

time.sleep(1)

# Motorpinnen
motor_links     = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links  = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links     = require_pin(board.get_pin('d:8:o'),  "brake_links D8")

motor_rechts    = require_pin(board.get_pin('d:3:p'),  "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts    = require_pin(board.get_pin('d:9:o'),  "brake_rechts D9")

time.sleep(1)

# ==========================
# Motor controller
# ==========================
class MotorController:
    def __init__(self, motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts,
                 base_left=BASE_SPEED_LEFT, base_right=BASE_SPEED_RIGHT,
                 min_left=MIN_PWM_LEFT, min_right=MIN_PWM_RIGHT):
        self.motor_links = motor_links
        self.motor_rechts = motor_rechts
        self.richting_links = richting_links
        self.richting_rechts = richting_rechts
        self.brake_links = brake_links
        self.brake_rechts = brake_rechts

        # individuele bases en minima
        self.base_left  = float(base_left)
        self.base_right = float(base_right)
        self.min_left   = float(min_left)
        self.min_right  = float(min_right)

        # standaard: vooruit, remmen uit
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.brake_links.write(0)
        self.brake_rechts.write(0)

    def _apply_deadzone(self, val, min_pwm):
        """
        Map elke >0 snelheid naar minstens min_pwm (anti-dode-zone).
        Laat exacte 0 door (echt stil).
        """
        val = float(val)
        if val <= 0.0:
            return 0.0
        return max(min_pwm, min(1.0, val))

    def set_speeds(self, left, right):
        # absolute PWM waarden 0..1 met anti-dode-zone
        left  = self._apply_deadzone(left,  self.min_left)
        right = self._apply_deadzone(right, self.min_right)
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def set_scaled(self, left_scale, right_scale):
        """
        Schaal t.o.v. eigen basis. Laat toe dat schaal > 1.0 is
        (boost buitenwiel), maar cap op 1.0 in set_speeds().
        """
        ls = self.base_left  * float(left_scale)
        rs = self.base_right * float(right_scale)
        self.set_speeds(ls, rs)

    def forward(self, scale=1.0):
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.set_scaled(scale, scale)

    def backward(self, scale=1.0):
        self.richting_links.write(1)
        self.richting_rechts.write(1)
        self.set_scaled(scale, scale)

    # ---------- Pivot (tegenroterend) draaien ----------
    def pivot_right(self, scale=0.9):
        """
        Rechtsom op de plek: linker wiel vooruit, rechter wiel achteruit.
        """
        self.richting_links.write(0)
        self.richting_rechts.write(1)
        outer = min(1.0, self.base_left  * scale * 1.4)  # boost voor effect
        inner = min(1.0, self.base_right * scale * 1.4)
        self.set_speeds(outer, inner)

    def pivot_left(self, scale=0.9):
        """
        Linksom op de plek: rechter wiel vooruit, linker wiel achteruit.
        """
        self.richting_links.write(1)
        self.richting_rechts.write(0)
        inner = min(1.0, self.base_left  * scale * 1.4)
        outer = min(1.0, self.base_right * scale * 1.4)
        self.set_speeds(inner, outer)

    # Achterwaartse milde bocht (optioneel)
    def back_arc_left(self, scale=0.6):
        self.richting_links.write(1)
        self.richting_rechts.write(1)
        self.set_scaled(scale * 0.4, scale)

    def back_arc_right(self, scale=0.6):
        self.richting_links.write(1)
        self.richting_rechts.write(1)
        self.set_scaled(scale, scale * 0.4)

    def stop(self):
        self.set_speeds(0, 0)

# ==========================
# Line Follower logica
# ==========================
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"

        # route state
        self.route_index = 0
        self.route_key = ROUTE_VOLGORDE[self.route_index]
        self.route_plan = ROUTES[self.route_key]["plan"]
        self.route_max = len(self.route_plan)
        self.route_step = 0
        self.last_turn_time = 0

    def read_sensors(self):
        """Leest de waarden van de globale sensor_values en vertaalt ze naar 0/1."""
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        print(f"Sens: {pattern}")
        return pattern

    def handle_crossings(self):
        """Check of we bij een kruispunt zijn en voer de geplande actie uit."""
        if self.route_step >= self.route_max:
            return False
        if time.time() - self.last_turn_time < CROSS_COOLDOWN:
            return False

        L1, L2, M, R2, R1 = self.read_sensors()

        # T of volledige kruising
        is_left_junction  = L1 == 1 and (L2 == 1 or M == 1)
        is_right_junction = R1 == 1 and (R2 == 1 or M == 1)
        is_cross          = L1 == 1 and R1 == 1

        if is_left_junction or is_right_junction or is_cross:
            pattern = [L1, L2, M, R2, R1]
            next_dir = self.route_plan[self.route_step]
            print(f"\nKRUISPUNT GEDETECTEERD (sensoren: {pattern}) - Route stap {self.route_step+1}/{self.route_max}: {next_dir}")
            self.choose(next_dir)
            self.route_step += 1
            self.last_turn_time = time.time()
            return True
        return False

    def spin_until_center(self, direction, scale=0.9, timeout=2.5):
        """
        Blijf draaien tot patroon [0,0,1,0,0] (midden) is gevonden,
        of tot 'timeout' seconden verstreken zijn (failsafe).
        Pivot (tegenroterend) voor maximale scherpte.
        """
        start = time.time()
        if direction == "left":
            self.mc.pivot_left(scale)
        else:
            self.mc.pivot_right(scale)

        while time.time() - start < timeout:
            pattern = self.read_sensors()
            if pattern in ([0,0,1,0,0], [0,1,1,0,0], [0,0,1,1,0]):
                self.mc.stop()
                print(f"  Midden gevonden na {direction} draai")
                return True
            time.sleep(0.01)

        self.mc.stop()
        print(f"  Timeout na {direction} draai")
        return False

    def choose(self, direction):
        """Voer de geplande route-actie uit."""
        if direction == "left":
            print("  Actie: Draai LINKS volgens route")
            self.mc.forward(1.0)
            time.sleep(0.10)
            self.spin_until_center("left", SHARP_TURN)
        elif direction == "right":
            print("  Actie: Draai RECHTS volgens route")
            self.mc.forward(1.0)
            time.sleep(0.10)
            self.spin_until_center("right", SHARP_TURN)
        else:
            print("  Actie: Ga RECHTDOOR volgens route")
            self.mc.forward(1.0)
            time.sleep(0.30)

    # ---- Nieuwe correctie helpers ----
    def correct_mild_left(self):
        # Binnenwiel knijpen, buitenwiel boosten
        self.mc.set_scaled(SMOOTH_TURN, min(1.4, 1.0 / self.mc.base_right))
        self.last_direction = "left"

    def correct_mild_right(self):
        self.mc.set_scaled(min(1.4, 1.0 / self.mc.base_left), SMOOTH_TURN)
        self.last_direction = "right"

    def correct_sharp_left(self):
        # Pivot links voor gegarandeerde draai
        self.mc.pivot_left(scale=SHARP_TURN)
        self.last_direction = "left"

    def correct_sharp_right(self):
        self.mc.pivot_right(scale=SHARP_TURN)
        self.last_direction = "right"

    def follow_line(self):
        """Volg de lijn en check eerst of we bij een kruispunt zijn."""
        # Eerst kruispuntafhandeling
        if self.handle_crossings():
            time.sleep(0.15)
            return

        L1, L2, M, R2, R1 = self.read_sensors()
        pattern = [L1, L2, M, R2, R1]

        # ---- Rechtuit / op lijn ----
        if pattern in (
            [0,0,1,0,0],   # midden exact
            [0,1,1,0,0],   # iets links
            [0,0,1,1,0],   # iets rechts
            [0,1,0,1,0],   # symmetrisch aangrenzend
            [0,1,1,1,0],   # brede lijn midden
        ):
            self.mc.forward(1.0)
            return

        # ---- Correctie links (mild) ----
        if pattern in (
            [0,1,0,0,0],   # lijn onder L2
            [1,1,0,0,0],   # L1 + L2 (maar geen midden)
        ):
            print("Correctie mild naar links")
            self.correct_mild_left()
            return

        # ---- Correctie rechts (mild) ----
        if pattern in (
            [0,0,0,1,0],   # lijn onder R2
            [0,0,0,1,1],   # R2 + R1
        ):
            print("Correctie mild naar rechts")
            self.correct_mild_right()
            return

        # ---- Correctie links (scherp) → buitenste sensor actief ----
        if pattern in (
            [1,0,0,0,0],   # alleen L1
            [1,0,1,0,0],   # L1 + M
        ):
            print("Correctie SCHERP naar links")
            self.correct_sharp_left()
            return

        # ---- Correctie rechts (scherp) → buitenste sensor actief ----
        if pattern in (
            [0,0,0,0,1],   # alleen R1
            [0,0,1,0,1],   # M + R1
        ):
            print("Correctie SCHERP naar rechts")
            self.correct_sharp_right()
            return

        # ---- Lijn verloren → recovery ----
        print("WAARSCHUWING: Lijn verloren - recovery actief")
        self.mc.backward(0.5)
        time.sleep(0.20)
        ok = self.spin_until_center(direction="right", scale=0.95, timeout=1.3)
        if not ok:
            ok = self.spin_until_center(direction="left", scale=0.95, timeout=1.3)

# ==========================
# Instanties
# ==========================
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts,
    base_left=BASE_SPEED_LEFT,
    base_right=BASE_SPEED_RIGHT,
    min_left=MIN_PWM_LEFT,
    min_right=MIN_PWM_RIGHT
)
lijnvolger = LineFollower(motor_controller)

# ==========================
# Signal handler voor nette exit
# ==========================
def signal_handler(sig, frame):
    print("\nStoppen...")
    try:
        motor_controller.stop()
    finally:
        board.exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ==========================
# (Optioneel) snelle zelftest
# ==========================
def quick_pivot_selftest(mc):
    print("\n=== QUICK PIVOT SELFTEST ===")
    print("Pivot RIGHT (links vooruit, rechts achteruit)")
    mc.pivot_right(0.9)
    time.sleep(0.7)
    mc.stop()
    time.sleep(0.3)
    print("Pivot LEFT  (rechts vooruit, links achteruit)")
    mc.pivot_left(0.9)
    time.sleep(0.7)
    mc.stop()
    print("=== EINDE SELFTEST ===\n")

# ==========================
# Main Loop
# ==========================
print("=" * 50)
print("Start lijnvolgen... (Ctrl+C om te stoppen)")
print(f"Route: {lijnvolger.route_key}")
print(f"Plan: {' -> '.join(lijnvolger.route_plan)}")
print(f"Totaal: {lijnvolger.route_max} stappen")
print("=" * 50)
time.sleep(1.0)

try:
    if SELFTEST:
        quick_pivot_selftest(motor_controller)
        # Zet hierna eventueel SELFTEST handmatig op False
    while True:
        lijnvolger.follow_line()
        time.sleep(MAIN_LOOP_SLEEP)
except KeyboardInterrupt:
    pass
finally:
    motor_controller.stop()
    board.exit()
    print("\nProgramma gestopt.")