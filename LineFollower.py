import time

from Config import SENSOR_THRESHOLD, CROSS_COOLDOWN, TURN_COOLDOWN, SPIN_TIMEOUT, POST_TURN_DELAY, ROUTES
from MotorController import MotorController, initialize_pin

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
        self.cooldown_duration = CROSS_COOLDOWN
        self.startup_boost_cycles = 2
    
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
        time.sleep(0.5)
        
        if direction == "left":
            self.motor.turn_left()
        else:
            self.motor.turn_right()
        
        time.sleep(0.1)
        
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
            # Zet gelijk wat correctie in om gecentreerd te blijven
            self.motor.forward(0.7)
    
    def handle_junction(self):
        """Detecteer kruispunt en voer route-instructie uit."""
        if self.route_step >= len(self.route_plan):
            print("\n✅ ROUTE VOLTOOID!")
            return False

        if time.time() - self.last_turn_time < self.cooldown_duration:
            return False

        sensors = self.read_sensors()

        if self.is_at_junction(*sensors):
            next_action = self.route_plan[self.route_step]
            print(f"\n🔀 KRUISPUNT #{self.route_step + 1}/{len(self.route_plan)}")

            self.execute_turn(next_action)

            self.route_step += 1
            self.last_turn_time = time.time()
            # Stel langere cooldown in na bochten voor stabilisatie
            if next_action in ["left", "right"]:
                self.cooldown_duration = TURN_COOLDOWN
            else:
                self.cooldown_duration = CROSS_COOLDOWN
            self.startup_boost_cycles = 10  # Activeer snelheid boost na turn
            return True

        return False
    
    def follow_line_correction(self):
        """Pas rijrichting aan om lijn te volgen."""
        left_outer, left_inner, middle, right_inner, right_outer = self.read_sensors()

        # Bepaal basis snelheden
        if left_inner and middle and right_inner:
            left_scale, right_scale = 1.0, 1.0
            print("Rechtdoor")
        elif left_outer and left_inner:
            left_scale, right_scale = 0.0, 1.0
            print("Middelmatige bocht naar links")
        elif left_inner and middle:
            left_scale, right_scale = 0.2, 0.6
            print("Kleine bocht naar links")
        elif right_inner and right_outer:
            left_scale, right_scale = 1.0, 0.0
            print("Middelmatige bocht naar rechts")
        elif middle and right_inner:
            left_scale, right_scale = 0.6, 0.2
            print("Kleine bocht naar rechts")
        elif left_outer:
            left_scale, right_scale = 0.0, 0.6
            print("Scherpe bocht naar links")
        elif right_outer:
            left_scale, right_scale = 0.6, 0.0
            print("Scherpe bocht naar rechts")
        elif middle and not (left_inner or right_inner or left_outer or right_outer):
            left_scale, right_scale = 1.0, 1.0
            print("Gecentreerd, rechtdoor")
        else:
            left_scale, right_scale = 0.6, 0.6
            print("Lijn kwijt! HELP!")

        # Pas startup boost toe indien actief
        if self.startup_boost_cycles > 0:
            left_scale *= 1.2
            right_scale *= 1.2
            self.startup_boost_cycles -= 1

        self.motor.set_speeds(left_scale, right_scale)
    
    def update(self):
        """Hoofdupdate cyclus: detecteer kruispunten of volg lijn."""
        if self.handle_junction():
            time.sleep(POST_TURN_DELAY)
            return
        
        self.follow_line_correction()
