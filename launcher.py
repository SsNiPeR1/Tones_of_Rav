import os
import subprocess
import signal
from config import *
import time

wholetime = bet_time + waiting_time + 60

while True:
    proc = subprocess.Popen(["python3", "main.py"])
    time.sleep(wholetime)
    os.kill(proc.pid, signal.SIGTERM)
    time.sleep(0.5)
    os.kill(proc.pid, signal.SIGTERM)
