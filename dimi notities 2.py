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

ARDUINO_PORT = 'COM3'
BASE_SPEED_LEFT = 0.23
BASE_SPEED_RIGHT = 0.23
SENSOR_THRESHOLD = 0.5

# KRITIEKE TIMING - NIET AANPASSEN ZONDER TESTEN
CROSS_COOLDOWN = 0.8  # VERHOOGD: Langere pauze tussen kruispunten
SPIN_TIMEOUT = 3.0
POST_TURN_DELAY = 0.3

ROUTES = {
    "depot-arcade": {
        "plan": ["right", "left", "straight"],
        "destination": "Arcade"
    },
    "depot-wildwaterbaan": {
        "plan": ["right", "straight", "straight", "left", "left", "straight"],
        "destination": "Wildwaterbaan"
    }, 
    "depot-achtbaan": {
        "plan": ["straight", "straight", "straight", "left", "straight"],
        "destination": "Achtbaan"
}}

ROUTE_SEQUENCE = ["depot-wildwaterbaan"]

# =============================================================================
# ARDUINO & SENSOR SETUP
# =============================================================================

def initialize_pin(pin, name):
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

def setup_arduino():
    board = Arduino(ARDUINO_PORT)
    iterator = util.Iterator(board)
    iterator.start()
    time.sleep(1)
    return board

def setup_sensors(board):
    sensor_values = [0.5] * 5
    
    def create_callback(index):
        def callback(data):
            if data is not None:
                sensor_values[index] = data
        return callback
    
    sensor_pins = [board.get_pin(f'a:{i}:i') for i in range(1, 6)]
    
    for i, pin in enumerate(sensor_pins):
        pin = initialize_pin(pin, f"Sensor A{i+1}")
        pin.register_callback(create_callback(i))
        pin.enable_reporting()
    
    time.sleep(1)
    return sensor_values

def setup_motors(board):
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
    def __init__(self, motor_config, base_left=BASE_SPEED_LEFT, base_right=BASE_SPEED_RIGHT):
        self.left = motor_config['left']
        self.right = motor_config['right']
        self.base_speed_left = float(base_left)
        self.base_speed_right = float(base_right)
        self.init_motors()
    
    def init_motors(self):
        for motor in [self.left, self.right]:
            motor['direction'].write(0)
            motor['brake'].write(0)
    
    def set_raw_speeds(self, left, right):
        left = max(0.0, min(1.0, float(left)))
        right = max(0.0, min(1.0, float(right)))
        self.left['pwm'].write(left)
        self.right['pwm'].write(right)
    
    def set_speeds(self, left_scale, right_scale):
        self.set_raw_speeds(
            self.base_speed_left * float(left_scale),
            self.base_speed_right * float(right_scale)
        )
    
    def forward(self, scale=1.0):
        self.left['direction'].write(0)
        self.right['direction'].write(0)
        self.set_speeds(scale, scale)
    
    def turn_right(self):
        self.left['direction'].write(0)
        self.right['direction'].write(1)
        self.set_raw_speeds(0.26, 0.26)
    
    def turn_left(self):
        self.left['direction'].write(1)
        self.right['direction'].write(0)
        self.set_raw_speeds(0.26, 0.26)
    
    def stop(self):
        self.set_raw_speeds(0, 0)

# =============================================================================
# LINE FOLLOWER LOGIC
# =============================================================================

class LineFollower:
    def __init__(self, motor_controller, sensor_values, route_key):
        self.motor = motor_controller
        self.sensors = sensor_values
        
        route = ROUTES[route_key]
        self.route_name = route_key
        self.route_plan = route["plan"]
        self.route_step = 0
        self.last_turn_time = 0
    
    def read_sensors(self):
        pattern = [1 if v < SENSOR_THRESHOLD else 0 for v in self.sensors]
        return pattern
    
    def is_at_junction(self, left_outer, left_inner, middle, right_inner, right_outer):
        is_left_junction = left_outer == 1 and (left_inner == 1 or middle == 1)
        is_right_junction = right_outer == 1 and (right_inner == 1 or middle == 1)
        is_full_cross = left_outer == 1 and right_outer == 1
        return is_left_junction or is_right_junction or is_full_cross
    
    def spin_until_centered(self, direction):
        """Draai tot lijn gecentreerd is."""
        start_time = time.time()
        self.motor.stop()
        time.sleep(0.15)
        
        if direction == "left":
            self.motor.turn_left()
        else:
            self.motor.turn_right()
        
        time.sleep(0.2)
        
        while time.time() - start_time < SPIN_TIMEOUT:
            if self.read_sensors() == [0, 0, 1, 0, 0]:
                self.motor.stop()
                print(f"  ✓ Gecentreerd ({direction})")
                return True
            time.sleep(0.02)
        
        self.motor.stop()
        print(f"  ! Timeout ({direction})")
        return False
    
    def execute_turn(self, direction):
        """Voer turn uit en zorg voor voldoende afstand."""
        print(f"  → {direction.upper()}")
        
        if direction == "right":
            self.motor.forward(1.0)
            time.sleep(0.25)
            self.spin_until_centered("right")
            time.sleep(0.15)
        
        elif direction == "left":
            self.motor.forward(1.0)
            time.sleep(0.25)
            self.spin_until_centered("left")
            time.sleep(0.15)
        
        else:  # straight
            self.motor.forward(1.0)
            time.sleep(0.5)
            self.motor.forward(0.6)
    
    def handle_junction(self):
        """Detecteer en verwerk kruispunten."""
        if self.route_step >= len(self.route_plan):
            print("\n✅ ROUTE VOLTOOID!")
            self.motor.stop()
            return False
        
        # STERKE cooldown om valse detecties te voorkomen
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
    
    def follow_line(self):
        """Volg de lijn."""
        l_o, l_i, m, r_i, r_o = self.read_sensors()
        
        # Gecentreerd
        if m and not l_i and not r_i:
            self.motor.forward(1.0)
        
        # Lichte links
        elif l_i and not l_o:
            self.motor.set_speeds(0.3, 1.0)
        
        # Lichte rechts
        elif r_i and not r_o:
            self.motor.set_speeds(1.0, 0.3)
        
        # Hard links
        elif l_o:
            self.motor.set_speeds(0.0, 1.0)
        
        # Hard rechts
        elif r_o:
            self.motor.set_speeds(1.0, 0.0)
        
        # Alleen middle
        elif m:
            self.motor.forward(0.7)
        
        # Lijn kwijt - rij voorzichtig
        else:
            self.motor.forward(0.4)
    
    def update(self):
        if self.handle_junction():
            time.sleep(POST_TURN_DELAY)
            return
        self.follow_line()

# =============================================================================
# MAIN PROGRAM
# =============================================================================

def setup_graceful_exit(motor_controller, board):
    def signal_handler(sig, frame):
        print("\n⏹ Gestopt")
        motor_controller.stop()
        board.exit()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

def print_route_info(follower):
    print("=" * 60)
    print("🤖 LINE FOLLOWER ROBOT")
    print("=" * 60)
    print(f"Route: {follower.route_name}")
    print(f"Plan: {' → '.join(follower.route_plan)}")
    print(f"Stappen: {len(follower.route_plan)}")
    print("=" * 60 + "\n")

def main():
    board = setup_arduino()
    sensor_values = setup_sensors(board)
    motor_config = setup_motors(board)
    
    motor_controller = MotorController(motor_config)
    line_follower = LineFollower(motor_controller, sensor_values, ROUTE_SEQUENCE[0])
    
    setup_graceful_exit(motor_controller, board)
    print_route_info(line_follower)
    
    time.sleep(2)
    
    try:
        while True:
            line_follower.update()
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        motor_controller.stop()
        board.exit()
        print("✓ Klaar")

if __name__ == "__main__":
    main()