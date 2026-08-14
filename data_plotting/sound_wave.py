import serial
import numpy as np
import matplotlib.pyplot as plt

print("Opening serial port...")
ser = serial.Serial("/dev/ttyACM0", 115200, timeout=2)

N = 188416  # number of bytes to receive

print("Serial port opened!")
print("Waiting for STM32...")

received = bytearray()

while len(received) < N:
    data = ser.read(N - len(received))

    if data:
        received.extend(data)
        print(f"Received {len(received)} / {N} bytes")

print("Finished receiving!")

# Convert raw bytes to uint32 samples
samples = np.frombuffer(received, dtype=np.uint32)

print(f"Number of samples: {len(samples)}")
print("First samples:", samples[:20])

# Create time axis
fs = 48000
t = np.arange(len(samples)) / fs

# Plot
plt.figure()
plt.plot(t, samples)
plt.xlabel("Time [s]")
plt.ylabel("Amplitude")
plt.title("Microphone data")
plt.grid()
plt.show()
