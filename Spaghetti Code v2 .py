from pyfirmata2 import Arduino, util
import time
import signal
import sys
import logging

# Configuratie
PORT = 'COM3'          # Pas aan indien nodig
BASE_SPEED = 0.17
SHARP_TURN = 0.8
SMOOTH_TURN = 0.5
THRESHOLD = 0.5        # drempel voor zwart/wit

# PID controller parameters
PID_KP = 0.2  # Proportional gain: response to current error strength
PID_KI = 0.01  # Integral gain: error correction over time
PID_KD = 0.2  # Derivative gain: dampening to reduce oscillation
INTEGRAL_CAP = 5.0


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
    
    def draaien(self, speed=BASE_SPEED * 0.8): # draait naar rechts
        self.richting_links.write(0)
        self.richting_rechts.write(1)
        self.motor_links.write(speed)
        self.motor_rechts.write(speed)

    def stop(self):
        self.motor_links.write(0)
        self.motor_rechts.write(0)

# PID Controller
class PIDController:
    """Handles PID calculations for line following"""
    
    def __init__(self):
        self.last_error = 0
        self.integral = 0
        
    def calculate(self, sensors):
        """Calculate motor speeds using PID control"""
        weights = [-2, -1, 0, 1, 2]
        inverted_sensors = [1 - s for s in sensors]
        
        if sum(inverted_sensors) == 0:
            error = self.last_error
        else:
            error = sum(w * s for w, s in zip(weights, inverted_sensors)) / sum(inverted_sensors)
        
        if abs(error) < 0.5:
            self.integral += error
            self.integral = max(-INTEGRAL_CAP, min(INTEGRAL_CAP, self.integral))
        
        derivative = error - self.last_error
        self.last_error = error
        
        adjustment = (PID_KP * error +
                      PID_KI * self.integral +
                      PID_KD * derivative)
        
        logging.info(f"PID: error={error:.3f}, integral={self.integral:.3f}, derivative={derivative:.3f}")
        
        left_speed = BASE_SPEED + adjustment
        right_speed = BASE_SPEED - adjustment
        
        min_speed = BASE_SPEED * 0.3
        left_speed = max(min_speed, min(1.0, left_speed))
        right_speed = max(min_speed, min(1.0, right_speed))
        
        return left_speed, right_speed

# Line Follower logica
class LineFollower:
    def __init__(self, motor_ctrl):
        self.mc = motor_ctrl
        self.last_direction = "straight"    

    def read_sensors(self):
        """Leest de waarden van de globale sensor_values en vertaalt ze naar 0/1."""
        pattern = [1 if v < THRESHOLD else 0 for v in sensor_values]
        return pattern

    def navigate_turn(self, direction, sharpness):
        """Bochtnavigatie met snelheidscompensatie."""
        if direction == "left":
            self.mc.set_speeds(BASE_SPEED * (1 - sharpness * 1.5),
                               BASE_SPEED * (1 + sharpness))
        elif direction == "right":
            self.mc.set_speeds(BASE_SPEED * (1 + sharpness),
                               BASE_SPEED * (1 - sharpness * 1.5))
    def follow_line(self):
        """Volg de lijn met PID-regeling."""
        sensors = sensor_values.copy()
        pid = PIDController()
        left_speed, right_speed = pid.calculate(sensors)
        self.mc.set_speeds(left_speed, right_speed)



# Instanties
motor_controller = MotorController(
    motor_links, motor_rechts,
    richting_links, richting_rechts,
    brake_links, brake_rechts
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