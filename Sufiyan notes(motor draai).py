from pyfirmata2 import Arduino
import time

board = Arduino('COM4')
board.samplingOn()

# LDR sensoren aansluiting
ldr_pins = ['a:1:i', 'a:2:i', 'a:3:i', 'a:4:i', 'a:5:i']
sensors = [board.get_pin(pin) for pin in ldr_pins]
ldr_values = [0.0] * 5

# Motoren aansluiting
motor_left = board.get_pin('d:3:p')  
motor_right = board.get_pin('d:11:p')  

# Sensorwaarden
def sensor_callback(value, index):
    ldr_values[index] = value

# Register callbacks
for i, sensor in enumerate(sensors):
    sensor.register_callback(lambda value, i=i: sensor_callback(value, i))
    sensor.enable_reporting()

def set_motor_speed(left_speed, right_speed):
    motor_left.write(left_speed)
    motor_right.write(right_speed)

def stop_robot():
    set_motor_speed(0, 0)

def is_intersection(vals, thr=0.4):
    return sum(1 for v in vals if v < thr) >= 4  # 4+ sensoren zwart = kruispunt

def follow_line():
    while True:
        print(f"Sensorwaarden: 1={ldr_values[0]:.2f}, 2={ldr_values[1]:.2f}, 3={ldr_values[2]:.2f}, 4={ldr_values[3]:.2f}, 5={ldr_values[4]:.2f}")
       
        s1, s2, s3, s4, s5 = ldr_values

        if is_intersection(ldr_values):
            print("Kruispunt gedetecteerd")
            stop_robot()
            time.sleep(0.5)
            set_motor_speed(0.4, 0.4)   # nu alleen even doorrollen

        else:
            if s2 < 0.4 and s3 < 0.4 and s4 < 0.4:
                set_motor_speed(0.4, 0.4)
                print("Rechtdoor")
            elif s1 < 0.4 and s2 < 0.4:
                set_motor_speed(0, 0.4)
                print("Middelmatige bocht links")
            elif s2 < 0.4 and s3 < 0.4:
                set_motor_speed(0.1, 0.3)
                print("Kleine bocht links")
            elif s4 < 0.4 and s5 < 0.4:
                set_motor_speed(0.4, 0)
                print("Middelmatige bocht rechts")
            elif s3 < 0.4 and s4 < 0.4:
                set_motor_speed(0.3, 0.1)
                print("Kleine bocht rechts")
            elif s1 < 0.4:
                set_motor_speed(0, 0.3)
                print("Scherpe bocht links")
            elif s5 < 0.4:
                set_motor_speed(0.3, 0)
                print("Scherpe bocht rechts")
            else:
                stop_robot()
                print("Lijn kwijt")
                time.sleep(1)
                set_motor_speed(0.4, 0.4)
                time.sleep(1)

        time.sleep(0.1)

if __name__ == "__main__":
    follow_line()