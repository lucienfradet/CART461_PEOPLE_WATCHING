"""
This file does:
- handle Serial data from the Arduino
- send and recieve that data between the two devices
- store the data in an object
- send the MPU (gyro) data of the other device to the arduino
"""

import serial
import socket
import threading
import time
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from shared_variables import config, local_osc, received_osc, update_local_osc, update_recieved_osc
from motor import MotorController

# Hardcoded configuration values
ARDUINO_SERIAL_PORT = "/dev/ttyACM0"
ARDUINO_BAUDRATE = 9600
OSC_IP = config['ip']['pi-ip']
OSC_SERVER_PORT = 8888
OSC_CLIENT_PORT = 9999

motor_controller = None

# Initialize serial connections with retry logic
def init_serial_connection(port, baudrate):
    while True:
        try:
            print(f"Attempting to connect to serial port: {port}")
            connection = serial.Serial(port, baudrate, timeout=1)
            print(f"Connected to serial port: {port}")
            time.sleep(2)  # Wait for Arduino to reset
            return connection
        except serial.SerialException as e:
            print(f"Failed to connect to serial port {port}: {e}. Retrying in 2 seconds...")
            time.sleep(2)

# Initialize serial connections
arduino_serial = init_serial_connection(ARDUINO_SERIAL_PORT, ARDUINO_BAUDRATE)

# OSC client and object storage
osc_client = None
# received_osc = {"y": 0, "z": 0, "pressure": False}
# local_osc = {"y": 0, "z": 0, "pressure": False}

# Initialize OSC client with retry logic
def init_osc_client(ip, port):
    while True:
        try:
            print(f"Attempting to connect to OSC server at {ip}:{port}")
            client = SimpleUDPClient(ip, port)
            print(f"Connected to OSC server at {ip}:{port}")
            return client
        except Exception as e:
            print(f"Failed to connect to OSC server at {ip}:{port}: {e}. Retrying in 2 seconds...")
            time.sleep(2)

osc_client = init_osc_client(OSC_IP, OSC_SERVER_PORT)

# Function to parse serial input
def parse_serial_line(line):
    try:
        parts = line.strip().split(", ")
        parsed = {}
        for part in parts:
            key, value = part.split(": ")
            if key in ["y", "z"]:
                parsed[key] = int(float(value))
            elif key == "pressure":
                parsed[key] = value == "1"
        return parsed
    except Exception as e:
        print(f"Error parsing line: {line}, Returning None!\n Error: {e}")
        return None

# Function to read serial data and send via OSC
def read_and_send_serial():
    global local_osc
    global received_osc
    global motor_controller
    while True:
        try:
            # Initialize variables
            line_done = False

            if not motor_controller.moving:
                # Request data by sending a dot
                arduino_serial.write(b".\n")  # Trigger the Arduino to send data

                # Read and process the line
                while not line_done:
                    line = arduino_serial.readline().decode('utf-8').strip()  # Decode bytes to string
                    if not line:  # Skip if the line is empty
                        print("no response from arduino.")
                        continue
                    
                    # print(f"Raw line from Arduino: {line}")
                    data = parse_serial_line(line)  # Parse the received line

                    if data:  # Process only if valid data is parsed
                        line_done = True  # Mark line as done

                        # Update the local OSC data
                        update_local_osc(data)

                        # Send parsed data via OSC
                        osc_client.send_message("/data", [data["y"], data["z"], int(data["pressure"])])
        except Exception as e:
            print(f"Error in read_and_send_serial: {e}")
            time.sleep(1)

# OSC handler function
def handle_osc_data(unused_addr, y, z, pressure):
    received_osc_temp = {"y": y, "z": z, "pressure": pressure}
    update_recieved_osc(received_osc_temp)
    # print(f"Received from OSC: {received_osc}")

# Set up OSC server with retry logic
def start_osc_server():
    while True:
        try:
            dispatcher = Dispatcher()
            dispatcher.map("/data", handle_osc_data)
            server = BlockingOSCUDPServer(("0.0.0.0", OSC_SERVER_PORT), dispatcher)
            print("OSC Server running...")
            server.serve_forever()
        except Exception as e:
            print(f"Error starting OSC server: {e}. Retrying in 2 seconds...")
            time.sleep(2)

def run_osc_handler():
    global motor_controller
    global arduino_serial
    motor_controller = MotorController(arduino_serial)
    motor_controller.start()
    threading.Thread(target=read_and_send_serial, daemon=True).start()
    start_osc_server()

if __name__ == "__main__":
    run_osc_handler()
