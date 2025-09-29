
import os, time, threading
from rfid_reader import loop as rfid_loop
from zone_beacon import loop as zone_loop
from tamper_sensor import loop as tamper_loop

threads = [
    threading.Thread(target=rfid_loop, daemon=True),
    threading.Thread(target=zone_loop, daemon=True),
    threading.Thread(target=tamper_loop, daemon=True)
]

for th in threads:
    th.start()

print("Simulators running: RFID + Zone + Tamper")
while True:
    time.sleep(1)
