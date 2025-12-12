from pyfirmata2 import Arduino
import time

board = Arduino('COM4')
board.samplingOn()

# LDR sensoren aansluiting
ldr_pins = ['a:1:i', 'a:2:i', 'a:3:i', 'a:4:i', 'a:5:i']
sensors = [board.get_pin(pin) for pin in ldr_pins]

# Motoren aansluiting
motor_left = board.get_pin('d:3:p')  
motor_right = board.get_pin('d:11:p')  
direction_right = board.get_pin('d:12:o')
direction_left = board.get_pin('d:13:o')

# Sensorwaarden
ldr_values = [0.0] * 5

def sensor_callback(value, index):
    global ldr_values
    ldr_values[index] = value

# Register callbacks
for i, sensor in enumerate(sensors):
    sensor.register_callback(lambda value, i=i: sensor_callback(value, i))
    sensor.enable_reporting()

def get_sensor_values():
    return {f"sensor_{i+1}": ldr_values[i] for i in range(5)}

def set_motor_speed(left_speed, right_speed):
    motor_left.write(left_speed)
    motor_right.write(right_speed)

def stop_robot():
    set_motor_speed(0, 0)

def turn_right():
    """Draai rechtsom (linker motor vooruit, rechter achteruit)."""
    direction_right.write(0)
    direction_left.write(1)
    set_motor_speed(0.5, 0.5)
    
def turn_left():
    """Draai linksom (rechter motor vooruit, linker achteruit)."""
    direction_right.write(1)
    direction_left.write(0)
    set_motor_speed(0.5, 0.5)


def follow_line():
    sensor_data = get_sensor_values()
    print(f"Sensorwaarden: 1={ldr_values[0]:.2f}, 2={ldr_values[1]:.2f}, 3={ldr_values[2]:.2f}, 4={ldr_values[3]:.2f}, 5={ldr_values[4]:.2f}")
   
    s1, s2, s3, s4, s5 = ldr_values

    if s2 < 0.5 and s3 < 0.5 and s4 < 0.5:
        set_motor_speed(0.5, 0.5)  
        print("Rechtdoor")
    elif s1 < 0.5 and s2 < 0.5:
        set_motor_speed(0, 0.5)
        print("Middelmatige bocht naar links")
    elif s2 < 0.5 and s3 < 0.5:
        set_motor_speed(0.1, 0.3)
        print("Kleine bocht naar links")
    elif s4 < 0.5 and s5 < 0.5:
        set_motor_speed(0.5, 0)
        print("Middelmatige bocht naar rechts")
    elif s3 < 0.5 and s4 < 0.5:
        set_motor_speed(0.3, 0.1)
        print("Kleine bocht naar rechts")
    elif s1 < 0.5:
        set_motor_speed(0, 0.3)
        print("Scherpe bocht naar links")
    elif s5 < 0.5:
        set_motor_speed(0.3, 0)
        print("Scherpe bocht naar rechts")
    else:
        stop_robot()
        print("Lijn kwijt! HELP!")
        set_motor_speed(0.3, 0.3)

if __name__ == "__main__":
    try:
        while True:
            follow_line()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n⚠ KeyboardInterrupt ontvangen...")
    finally:
        stop_robot()
        board.exit()
        print("✓ Programma gestopt.")