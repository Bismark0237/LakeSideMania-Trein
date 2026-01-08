import time

from Config import BASE_SPEED_LEFT, BASE_SPEED_RIGHT

def initialize_pin(pin, name):
    """Controleer of een pin correct is geïnitialiseerd."""
    if pin is None:
        raise RuntimeError(f"Pin '{name}' kon niet worden geïnitialiseerd.")
    return pin

def setup_motors(board):
    """Configureer motorpinnen voor beide motoren."""
    motor_config = {
        'left': {
            'pwm': initialize_pin(board.get_pin('d:11:p'), "Motor Links PWM"),
            'direction': initialize_pin(board.get_pin('d:13:o'), "Motor Links Richting"),
        },
        'right': {
            'pwm': initialize_pin(board.get_pin('d:3:p'), "Motor Rechts PWM"),
            'direction': initialize_pin(board.get_pin('d:12:o'), "Motor Rechts Richting"),
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
        self.left['direction'].write(1)
        self.right['direction'].write(0)
        self.set_raw_speeds(0.4, 0.4)
    
    def turn_left(self):
        """Draai linksom (rechter motor vooruit, linker achteruit)."""
        self.left['direction'].write(0)
        self.right['direction'].write(1)
        self.set_raw_speeds(0.4, 0.4)
    
    def stop(self):
        """Stop beide motoren."""
        self.set_raw_speeds(0, 0)
