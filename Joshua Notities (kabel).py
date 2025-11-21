"""
Line Follower Robot Controller
Bestuurt een robot die een lijn volgt en vooraf geprogrammeerde routes aflegt.
"""

from pyfirmata2 import Arduino, util
import time
import signal
import sys

# =============================================================================
# CONFIGURATIE
# =============================================================================

# Arduino verbinding
ARDUINO_PORT = 'COM3'

# Motor kalibratie (aangepast voor individuele motorverschillen)
BASE_SPEED_LEFT = 0.2
BASE_SPEED_RIGHT = 0.2

# Sensor drempelwaarde voor zwart/wit detectie
SENSOR_THRESHOLD = 0.5

# Timing constanten
CROSS_COOLDOWN = 0.5  # Verkort voor betere kruispuntdetectie
SPIN_TIMEOUT = 2.5    # Maximale tijd voor draai-operatie
POST_TURN_DELAY = 0.5  # Vertraging na turn voor stabiele detectie

# Route definities
ROUTES = {
    "depot-arcade": {
        "plan": ["right", "left", "stop"],
        "destination": "Arcade"
    },
    "depot-wildwaterbaan": {
        "plan": ["right", "straight", "straight", "left", "left", "stop"],
        "destination": "Wildwaterbaan"
    }, 
    "depot-achtbaan": {
        "plan": ["straight", "straight", "straight", "left", "stop"],
        "destination": "Achtbaan"
}}

ROUTE_SEQUENCE = ["depot-achtbaan"]

# =============================================================================
# ARDUINO & SENSOR SETUP
# =============================================================================

def initialize_pin(pin, name):
    """Controleer of een pin correct is geïnitialiseerd."""
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin


def setup_arduino():
    """Initialiseer Arduino board en start de iterator."""
    board = Arduino(ARDUINO_PORT)
    iterator = util.Iterator(board)
    iterator.start()
    time.sleep(1)
    return board


def setup_sensors(board):
    """Configureer de 5 lijnsensoren met callbacks."""
    sensor_values = [0.5] * 5  # Neutrale startwaarden
    
    def create_callback(index):
        """Factory functie voor sensor callbacks."""
        def callback(data):
            if data is not None:
                sensor_values[index] = data
        return callback
    
    # Initialiseer analoge sensoren A1 t/m A5
    sensor_pins = [board.get_pin(f'a:{i}:i') for i in range(1, 6)]
    
    for i, pin in enumerate(sensor_pins):
        pin = initialize_pin(pin, f"Sensor A{i+1}")
        pin.register_callback(create_callback(i))
        pin.enable_reporting()
    
    time.sleep(1)
    return sensor_values


def setup_motors(board):
    """Configureer motorpinnen voor beide motoren."""
    motor_config = {
        'left': {
            'pwm': initialize_pin(board.get_pin('d:11:p'), "Motor Links PWM"),
            'direction': initialize_pin(board.get_pin('d:13:o'), "Motor Links Richting"),
            'brake': initialize_pin(board.get_pin('d:8:o'), "Motor Links Rem")
        },
        'right': {
            'pwm': initialize_pin(board.get_pin('d:3:p'), "Motor Rechts PWM"),
            'direction': initialize_pin(board.get_pin('d:12:o'), "Motor Rechts Richting"),
            'brake': initialize_pin(board.get_pin('d:9:o'), "Motor Rechts Rem")
        }
    }
    time.sleep(1)
    return motor_config


# =============================================================================
# MOTOR CONTROLLER
# =============================================================================

class MotorController:
    """Bestuurt beide motoren met individuele snelheidskalibratie."""
    
    def __init__(self, motor_config, base_left=BASE_SPEED_LEFT, base_right=BASE_SPEED_RIGHT):
        self.left = motor_config['left']
        self.right = motor_config['right']
        self.base_speed_left = float(base_left)
        self.base_speed_right = float(base_right)
        
        # Initiële staat: vooruit, remmen uit
        self.init_motors()
    
    def init_motors(self):
        """Zet motoren in initiële staat."""
        for motor in [self.left, self.right]:
            motor['direction'].write(0)
            motor['brake'].write(0)
    
    def set_raw_speeds(self, left, right):
        """Zet absolute PWM waarden (0.0 - 1.0)."""
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.left['pwm'].write(left)
        self.right['pwm'].write(right)
    
    def set_speeds(self, left_scale, right_scale):
        """Zet snelheden als factor van basis snelheid."""
        self.set_raw_speeds(
            self.base_speed_left * float(left_scale),
            self.base_speed_right * float(right_scale)
        )
    
    def forward(self, scale=1.0):
        """Rij vooruit met optionele snelheidsschaling."""
        self.left['direction'].write(0)
        self.right['direction'].write(0)
        self.set_speeds(scale, scale)
    
    def turn_right(self):
        """Draai rechtsom (linker motor vooruit, rechter achteruit)."""
        self.left['direction'].write(0)
        self.right['direction'].write(1)
        self.set_raw_speeds(0.22, 0.22)
    
    def turn_left(self):
        """Draai linksom (rechter motor vooruit, linker achteruit)."""
        self.left['direction'].write(1)
        self.right['direction'].write(0)
        self.set_raw_speeds(0.25, 0.25)
    
    def stop(self):
        """Stop beide motoren."""
        self.set_raw_speeds(0, 0)


# =============================================================================
# LINE FOLLOWER LOGIC
# =============================================================================

class LineFollower:
    """Hoofdlogica voor lijnvolgen en route navigatie."""
    
    def __init__(self, motor_controller, sensor_values, route_key):
        self.motor = motor_controller
        self.sensors = sensor_values
        
        # Route informatie
        route = ROUTES[route_key]
        self.route_name = route_key
        self.route_plan = route["plan"]
        self.route_step = 0
        self.last_turn_time = 0
    
    def read_sensors(self):
        """Converteer analoge sensorwaarden naar binair patroon (0=wit, 1=zwart)."""
        pattern = [1 if v < SENSOR_THRESHOLD else 0 for v in self.sensors]
        print(f"Sensoren: {pattern}")
        return pattern
    
    def is_at_junction(self, left_outer, left_inner, middle, right_inner, right_outer):
        """Detecteer of robot bij een T-kruispunt of kruising is."""
        is_left_junction = left_outer == 1 and (left_inner == 1 or middle == 1)
        is_right_junction = right_outer == 1 and (right_inner == 1 or middle == 1)
        is_full_cross = left_outer == 1 and right_outer == 1
        
        return is_left_junction or is_right_junction or is_full_cross
    
    def spin_until_centered(self, direction):
        """Draai totdat de lijn gecentreerd is (patroon [0,0,1,0,0])."""
        start_time = time.time()
        
        # Start draaibeweging
        self.motor.stop()
        time.sleep(0.5)
        
        if direction == "left":
            self.motor.turn_left()
        else:
            self.motor.turn_right()
        
        time.sleep(0.4)
        
        # Zoek gecentreerde positie
        while time.time() - start_time < SPIN_TIMEOUT:
            if self.read_sensors() == [0, 0, 1, 0, 0]:
                self.motor.stop()
                print(f"  ✓ Lijn gecentreerd na {direction} draai")
                return True
            time.sleep(0.01)
        
        self.motor.stop()
        print(f"  ✗ Timeout bij {direction} draai")
        return False
    
    def execute_turn(self, direction):
        """Voer route-instructie uit op kruispunt."""
        print(f"  → Uitvoeren: {direction.upper()}")
        
        if direction in ["left", "right"]:
            self.motor.forward()
            time.sleep(0.15)
            self.motor.stop()
            time.sleep(0.4)
            self.spin_until_centered(direction)
        elif direction == "stop":
            self.motor.forward()
            time.sleep(2)
            self.motor.stop()
            time.sleep(5)
            print("  ■ Robot gestopt op bestemming.")
        else:  # straight
            # Rij het kruispunt voorbij en stabiliseer
            self.motor.forward(1.0)
            time.sleep(0.35)
            # Zet gelijk wat correctie in om gecentreerd te blijven
            self.motor.forward(0.7)
    
    def handle_junction(self):
        """Detecteer kruispunt en voer route-instructie uit."""
        if self.route_step >= len(self.route_plan):
            print("\n✅ ROUTE VOLTOOID!")
            return False
        
        if time.time() - self.last_turn_time < CROSS_COOLDOWN:
            return False
        
        sensors = self.read_sensors()
        
        if self.is_at_junction(*sensors):
            next_action = self.route_plan[self.route_step]
            print(f"\n🔀 KRUISPUNT #{self.route_step + 1}/{len(self.route_plan)}")
            
            self.execute_turn(next_action)
            
            self.route_step += 1
            self.last_turn_time = time.time()
            return True
        
        return False
    
    def follow_line_correction(self):
        """Pas rijrichting aan om lijn te volgen."""
        left_outer, left_inner, middle, right_inner, right_outer = self.read_sensors()
        
        # Perfect gecentreerd - volle snelheid vooruit
        if middle and not left_inner and not right_inner:
            self.motor.forward(1.0)
        
        # Lichte afwijking links (inner sensor)
        elif left_inner and not left_outer:
            self.motor.set_speeds(0.2, 0.8)
        
        # Lichte afwijking rechts (inner sensor)
        elif right_inner and not right_outer:
            self.motor.set_speeds(0.8, 0.2)
        
        # Sterke afwijking links (outer sensor actief)
        elif left_outer:
            self.motor.set_speeds(0.1, 0.9)
        
        # Sterke afwijking rechts (outer sensor actief)
        elif right_outer:
            self.motor.set_speeds(0.9, 0.1)
        
        # Middle sensor alleen (kan gebeuren bij bochten)
        elif middle:
            self.motor.forward(0.7)
        
        # Lijn volledig kwijt - noodsituatie
        else:
            self.motor.stop()
            print("  ⚠ Lijn kwijt! Recover...")
            time.sleep(0.1)
    
    def update(self):
        """Hoofdupdate cyclus: detecteer kruispunten of volg lijn."""
        if self.handle_junction():
            time.sleep(POST_TURN_DELAY)
            return
        
        self.follow_line_correction()


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def setup_graceful_exit(motor_controller, board):
    """Configureer netjes afsluiten bij Ctrl+C."""
    def signal_handler(sig, frame):
        print("\n\n⏹ Stoppen...")
        motor_controller.stop()
        board.exit()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)


def print_route_info(follower):
    """Toon route informatie bij opstarten."""
    print("=" * 60)
    print("🤖 LINE FOLLOWER ROBOT - START")
    print("=" * 60)
    print(f"Route: {follower.route_name}")
    print(f"Plan: {' → '.join(follower.route_plan)}")
    print(f"Totaal stappen: {len(follower.route_plan)}")
    print("=" * 60)
    print("Druk Ctrl+C om te stoppen\n")


def main():
    """Hoofdprogramma."""
    # Initialisatie
    board = setup_arduino()
    sensor_values = setup_sensors(board)
    motor_config = setup_motors(board)
    
    motor_controller = MotorController(motor_config)
    line_follower = LineFollower(motor_controller, sensor_values, ROUTE_SEQUENCE[0])
    
    setup_graceful_exit(motor_controller, board)
    print_route_info(line_follower)
    
    time.sleep(2)
    
    # Main loop
    try:
        while True:
            line_follower.update()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        motor_controller.stop()
        board.exit()
        print("\n✓ Programma gestopt.")


if __name__ == "__main__":
    main()