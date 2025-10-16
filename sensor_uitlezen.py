from pyfirmata2 import Arduino, util
import time

board = Arduino('COM3')

# Maak een lijst met je analoge sensoren
sensor_L1 = board.get_pin('a:1:i')  # Analog pin voor ver links
sensor_L2 = board.get_pin('a:2:i')  # Analog pin voor links
sensor_M = board.get_pin('a:3:i')  # Analog pin voor midden
sensor_R2 = board.get_pin('a:4:i')  # Analog pin voor rechts
sensor_R1 = board.get_pin('a:5:i')  # Analog pin voor ver rechts

class SensorManager:
    """Manages the robot's sensors and provides readings"""
    
    def __init__(self, board):
        self.board = board
        self.sensors = {}
        self.sensor_values = {}
        self.prev_readings = [1, 1, 1, 1, 1]
        self.last_valid_pattern = None
        
    def setup(self):
        """Initialize and set up the sensors"""
        try:
            for i in range(5):
                sensor_name = f'sensor_{i}'
                pin = self.board.get_pin(f'a:{i}:i')
                pin.register_callback(self.create_callback(sensor_name))
                pin.enable_reporting()
                self.sensors[sensor_name] = pin
            return True
        except Exception as e:
            logging.error(f"Sensor setup failed: {e}")
            return False
            
    def create_callback(self, sensor_name):
        """Create callback function for sensor reading"""
        def callback(value):
            self.sensor_values[sensor_name] = value
        return callback
        
    def read_sensors(self):
        """Read current sensor values and return binary array"""
        try:
            readings = [
                1 if self.sensor_values.get(f'sensor_{i}', 1) > SENSOR_THRESHOLD else 0
                for i in range(5)
            ]
            self.prev_readings = readings.copy()
            
            # Update last valid pattern if we see something
            if not all(s == 1 for s in readings):
                self.last_valid_pattern = readings.copy()
                
            return readings
        except Exception as e:
            logging.error(f"Sensor reading error: {e}")
            return self.prev_readings.copy()
            
    @staticmethod
    def detect_junction(sensors):
        """Detect if robot is at a junction"""
        black_count = sum(1 for s in sensors if s == 0)
        return black_count >= MIN_BLACK_SENSORS_JUNCTION
        
    @staticmethod
    def detect_line_lost(sensors):
        """Detect if line is lost (all sensors see white)"""
        return all(s == 1 for s in sensors)