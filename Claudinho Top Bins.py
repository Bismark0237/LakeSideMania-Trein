from pyfirmata2 import Arduino, util
import time
import signal
import sys

# Configuratie
PORT = 'COM3'          # Pas aan indien nodig

# Aparte basis-snelheden per motor
BASE_SPEED_LEFT = 0.18     # linker motor basis
BASE_SPEED_RIGHT = 0.23    # rechter motor basis

SHARP_TURN = 0.8
SMOOTH_TURN = 0.5
THRESHOLD = 0.5        # drempel voor zwart/wit
CROSS_COOLDOWN = 0.5   # s na bocht geen nieuwe kruispuntbeslissing (verlaagd voor snellere detectie)
ROUTES = {
    "depot-achtbaan": {"plan": ["straight", "straight", "straight", "straight", "straight", "left", "straight"], "loc": "Trein depot"},
}
ROUTE_VOLGORDE = [
    "depot-achtbaan"
]

# Pin checker
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

# Arduino setup
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
    s = require_pin(s, f"sensor A{i}")
    s.register_callback(maak_callback(i))
    s.enable_reporting()

time.sleep(1)

# Motorpinnen
motor_links = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links = require_pin(board.get_pin('d:8:o'), "brake_links D8")

motor_rechts = require_pin(board.get_pin('d:3:p'), "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts = require_pin(board.get_pin('d:9:o'), "brake_rechts D9")

time.sleep(1)

# Motor controller
class MotorController:
    def __init__(self, motor_links, motor_rechts, richting_links, richting_rechts, brake_links, brake_rechts,
                 base_left=BASE_SPEED_LEFT, base_right=BASE_SPEED_RIGHT):
        self.motor_links = motor_links
        self.motor_rechts = motor_rechts
        self.richting_links = richting_links
        self.richting_rechts = richting_rechts
        self.brake_links = brake_links
        self.brake_rechts = brake_rechts

        # individuele bases
        self.base_left = float(base_left)
        self.base_right = float(base_right)

        # standaard: vooruit, remmen uit
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.brake_links.write(0)
        self.brake_rechts.write(0)

    def set_speeds(self, left, right):
        # absolute PWM waarden 0..1
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.motor_links.write(left)
        self.motor_rechts.write(right)

    def set_scaled(self, left_scale, right_scale):
        # schaal t.o.v. eigen basis
        self.set_speeds(self.base_left * float(left_scale),
                        self.base_right * float(right_scale))

    def forward(self, scale=1.0):
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.set_scaled(scale, scale)

    def backward(self, scale=1.0):
        self.richting_links.write(1)
        self.richting_rechts.write(1)
        self.set_scaled(scale, scale)

    def draaien(self, scale=0.8):
        """Rechtsom draaien door left trager, rechts sneller."""
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.motor_links.write(0.2)
        self.motor_rechts.write(0)

    def draaien_tegen(self, scale=0.8):
        """Linksom draaien door left sneller, rechts trager."""
        self.richting_links.write(0)
        self.richting_rechts.write(0)
        self.motor_links.write(0)
        self.motor_rechts.write(0.2)

    def stop(self):
        self.set_speeds(0, 0)

# Line Follower logica
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
        self.last_turn_time = 0  # FIX: Initialiseer deze variabele

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
        
        # Detecteer T-kruispunt: buitenste sensoren (L1 of R1) actief + middelste sensoren
        # Dit onderscheidt kruispunten van normale bochten
        is_left_junction = L1 == 1 and (L2 == 1 or M == 1)
        is_right_junction = R1 == 1 and (R2 == 1 or M == 1)
        is_cross = L1 == 1 and R1 == 1  # volledige kruising
        
        if is_left_junction or is_right_junction or is_cross:
            pattern = [L1, L2, M, R2, R1]
            next_dir = self.route_plan[self.route_step]
            print(f"\nKRUISPUNT GEDETECTEERD (sensoren: {pattern}) - Route stap {self.route_step+1}/{self.route_max}: {next_dir}")
            self.choose(next_dir)
            self.route_step += 1
            self.last_turn_time = time.time()
            return True
        return False

    def spin_until_center(self, direction, scale=0.8, timeout=2.5):
        """
        Blijf draaien tot patroon [0,0,1,0,0] (midden) is gevonden,
        of tot 'timeout' seconden verstreken zijn (failsafe).
        """
        start = time.time()
        if direction == "left":
            self.mc.draaien_tegen(scale)
        else:
            self.mc.draaien(scale)

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
            # Eerst even vooruit om kruispunt beter in te rijden
            self.mc.forward(1.0)
            time.sleep(0.15)
            self.spin_until_center("left", SHARP_TURN)
        elif direction == "right":
            print("  Actie: Draai RECHTS volgens route")
            # Eerst even vooruit om kruispunt beter in te rijden
            self.mc.forward(1.0)
            time.sleep(0.15)
            self.spin_until_center("right", SHARP_TURN)
        else:
            print("  Actie: Ga RECHTDOOR volgens route")
            # Kort vooruit om kruispunt te passeren
            self.mc.forward(1.0)
            time.sleep(0.4)

    def follow_line(self):
        """Volg de lijn en check eerst of we bij een kruispunt zijn."""
        
        # BELANGRIJKSTE FIX: Check eerst of we bij een kruispunt zijn
        if self.handle_crossings():
            # Na kruispunt even doorgaan voordat we weer normale lijnvolg-logica doen
            time.sleep(0.2)
            return
        
        L1, L2, M, R2, R1 = self.read_sensors()
        pattern = [L1, L2, M, R2, R1]

        # Straight
        if pattern in ([0,0,1,0,0], [0,1,1,1,0], [0,0,1,1,0], [0,1,1,0,0], [0,1,0,1,0]):
            self.mc.forward(1.0)

        # Correctie left
        elif pattern in ([0,1,0,0,0], [1,1,0,0,0], [1,0,0,0,0], [1,1,0,0,0]):
            print("Correctie naar left")
            self.mc.set_scaled(SMOOTH_TURN, 1.0)
            # self.last_direction = "left"
        
        # Correctie rechts
        elif pattern in ([0,0,0,1,0], [0,0,1,1,0], [0,0,0,0,1], [0,0,0,1,1]):
            print("Correctie naar rechts")
            self.mc.set_scaled(1.0, SMOOTH_TURN)
            # self.last_direction = "right"

        # Lijn verloren - recovery
        else:
            print("WAARSCHUWING: Lijn verloren - recovery actief")
            self.mc.backward(0.5)
            time.sleep(0.25)
            ok = self.spin_until_center(direction="right", scale=0.8, timeout=1.5)
            if not ok:
                ok = self.spin_until_center(direction="left", scale=0.8, timeout=1.5)


# Instanties
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts,
    base_left=BASE_SPEED_LEFT,
    base_right=BASE_SPEED_RIGHT
)
lijnvolger = LineFollower(motor_controller)

# Signal handler voor nette exit
def signal_handler(sig, frame):
    print("\nStoppen...")
    try:
        motor_controller.stop()
    finally:
        board.exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Main Loop
print("=" * 50)
print("Start lijnvolgen... (Ctrl+C om te stoppen)")
print(f"Route: {lijnvolger.route_key}")
print(f"Plan: {' -> '.join(lijnvolger.route_plan)}")
print(f"Totaal: {lijnvolger.route_max} stappen")
print("=" * 50)
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
    print("\nProgramma gestopt.")