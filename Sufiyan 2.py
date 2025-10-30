from pyfirmata2 import Arduino, util
import time
import signal
import sys

# =========================================
# Configuratie
# =========================================
PORT = 'COM3'          # Pas aan indien nodig
BASE_SPEED = 0.8
SHARP_TURN = 0.8
SMOOTH_TURN = 0.5
THRESHOLD = 0.5        # drempel voor zwart/wit

# Routeplan (voorbeeld: Achtbaan)
# Elke entry = actie bij het VOLGENDE kruispunt.
# geldige acties: "rechtdoor", "links", "rechts", "halte"
ROUTE_STEPS = ["rechtdoor", "rechtdoor", "rechtdoor", "links", "halte"]
current_step_index = 0  # we beginnen bij stap 0


# =========================================
# Helpers
# =========================================
def require_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin


# =========================================
# Arduino setup
# =========================================
board = Arduino(PORT)
it = util.Iterator(board)
it.start()
time.sleep(1)

# Sensoren (lijnsensoren)
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

# (optioneel / placeholder) Obstakel-sensor
# Bijvoorbeeld ultrasoon of IR. Voor nu None -> je kunt later koppelen.
obstacle_sensor = None   # board.get_pin('a:0:i') of iets dergelijks


# =========================================
# Motorpinnen
# =========================================
motor_links = require_pin(board.get_pin('d:11:p'), "motor_links PWM D11")
richting_links = require_pin(board.get_pin('d:13:o'), "richting_links D13")
brake_links = require_pin(board.get_pin('d:8:o'), "brake_links D8")

motor_rechts = require_pin(board.get_pin('d:3:p'), "motor_rechts PWM D3")
richting_rechts = require_pin(board.get_pin('d:12:o'), "richting_rechts D12")
brake_rechts = require_pin(board.get_pin('d:9:o'), "brake_rechts D9")

time.sleep(1)


# =========================================
# Motor controller
# =========================================
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
    
    def draaien_rechts(self, speed=BASE_SPEED * 0.8):
        """draait op de plaats naar rechts"""
        self.richting_links.write(0)
        self.richting_rechts.write(1)
        self.motor_links.write(speed)
        self.motor_rechts.write(speed)

    def draaien_links(self, speed=BASE_SPEED * 0.8):
        """draait op de plaats naar links"""
        self.richting_links.write(1)
        self.richting_rechts.write(0)
        self.motor_links.write(speed)
        self.motor_rechts.write(speed)

    def stop(self):
        self.motor_links.write(0)
        self.motor_rechts.write(0)


# =========================================
# Line Follower logica
# =========================================
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"

    def read_sensors(self):
        """Leest de waarden van de globale sensor_values en vertaalt ze naar 0/1."""
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        return pattern

    def check_obstacle(self):
        """Checkt of er een obstakel is.
           TODO: later koppelen aan echte sensorwaarde.
           Voor nu: altijd False zodat code wel runt.
        """
        if obstacle_sensor is None:
            return False
        val = obstacle_sensor.read()
        # Je zou hier drempel logica doen, bv val < 0.3 => obstakel dichtbij
        return False

    def navigate_turn(self, direction, sharpness):
        """Bochtnavigatie met snelheidscompensatie."""
        if direction == "left":
            self.mc.set_speeds(BASE_SPEED * (1 - sharpness * 1.5),
                               BASE_SPEED * (1 + sharpness))
        elif direction == "right":
            self.mc.set_speeds(BASE_SPEED * (1 + sharpness),
                               BASE_SPEED * (1 - sharpness * 1.5))

    def handle_intersection(self):
        """Wordt aangeroepen zodra we een kruispunt zien.
           Voert de juiste actie uit volgens ROUTE_STEPS[current_step_index].
        """
        global current_step_index

        # Obstacle check heeft prioriteit (veiligheid > route)
        if self.check_obstacle():
            print("OBSTAKEL bij kruispunt -> STOP")
            self.mc.stop()
            time.sleep(2)
            return

        # Als er geen stappen meer zijn, beschouw dit als halte / routepunt
        if current_step_index >= len(ROUTE_STEPS):
            print("Geen verdere stappen -> halte / eindpunt")
            self.mc.stop()
            time.sleep(3)
            return

        actie = ROUTE_STEPS[current_step_index]
        print(f"Kruispunt #{current_step_index} actie = {actie}")

        # eerst stoppen (passagiersmoment / nadenken)
        self.mc.stop()
        time.sleep(1)

        if actie == "rechtdoor":
            print("→ Rechtdoor")
            self.mc.forward(BASE_SPEED)
            self.last_direction = "straight"

        elif actie == "links":
            print("→ Linksaf nemen")
            # draai op de plaats naar links
            self.mc.draaien_links(BASE_SPEED * 0.7)
            time.sleep(0.4)  # finetunen op ec