# LUMEN CORE - Node G (Gateway, ESP32 #1)   MAC: D4:E9:F4:A3:F1:5C
# Save to the gateway ESP32 as main.py
#
# Wiring:
#   ESP32 TX2 (GPIO17) -> Nucleo D2 (PA10, USART1 RX)
#   ESP32 RX2 (GPIO16) <- Nucleo D8 (PA9,  USART1 TX)
#   ESP32 GND          -- Nucleo GND  (common ground is mandatory)
#   Flame sensor DO   -> GPIO34     (VCC on 3.3V)
#   LED               -> GPIO5 -> 220R -> GND
#
# Accepts from nodes A/B/C:  N<id>,<seq>,<value>,<D|R>[,<pdr%>]
# Forwards the line unchanged to the STM32 (the STM32 code needs no change).

import network, espnow, time
from machine import Pin, UART

# --- Radio: station mode, NOT connected to any AP, so the channel stays fixed
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
try:
    sta.config(pm=network.WLAN.PM_NONE)   # no power-save: don't miss packets
except Exception:
    pass

MY_MAC = b'\xd4\xe9\xf4\xa3\xf1\x5c'      # D4:E9:F4:A3:F1:5C - nodes must use this as GATEWAY_MAC
mac = sta.config('mac')
print("Gateway MAC:", ":".join("{:02X}".format(b) for b in mac))
if mac != MY_MAC:
    print("WARNING: this is not the board D4:E9:F4:A3:F1:5C - nodes will not reach it!")

e = espnow.ESPNow()
e.active(True)
# Gateway only receives (and auto-acks), so nodes don't need to be added as peers.

# --- UART2 to STM32
uart = UART(2, baudrate=115200, tx=17, rx=16)

NODE_ID       = "G"
REPORT_MS     = 2000      # own flame report every 2 s
RELAY_HOLD_MS = 8000      # LED stays on 8 s after the last relayed packet
VALID_IDS     = ("A", "B", "C")

flame = Pin(34, Pin.IN)   # GPIO34 input-only
led   = Pin(5, Pin.OUT)
led.value(0)


def emit(line):
    uart.write(line + "\n")      # STM32 splits lines on '\n'
    print(line)


def valid(text):
    """Accept N<id>,<seq>,<value>,<D|R> or N<id>,<seq>,<value>,<D|R>,<pdr 0..100>."""
    parts = text.split(",")
    if len(parts) not in (4, 5):
        return False
    tag, seq, val, route = parts[0], parts[1], parts[2], parts[3]
    if len(tag) != 2 or tag[0] != "N" or tag[1] not in VALID_IDS:
        return False
    if route not in ("D", "R"):
        return False
    try:
        int(seq)
        float(val)
        if len(parts) == 5:
            p = int(parts[4])
            if p < 0 or p > 100:
                return False
    except ValueError:
        return False
    return True


def read_flame():
    # Most flame modules pull DO LOW when flame is detected. Flip if yours is opposite.
    return 1 if flame.value() == 0 else 0


seq = 0
last_report = time.ticks_add(time.ticks_ms(), -REPORT_MS)
last_relay = None

while True:
    try:
        host, msg = e.recv(100)          # wait up to 100 ms for a mesh packet
    except OSError:
        host, msg = None, None

    if msg:
        try:
            text = msg.decode().strip()
        except Exception:
            text = ""
        if valid(text):
            emit(text)
            if text.split(",")[3] == "R":
                last_relay = time.ticks_ms()
        # b'PROBE' and noise are dropped

    now = time.ticks_ms()

    if time.ticks_diff(now, last_report) >= REPORT_MS:
        last_report = now
        seq += 1
        emit("N{},{},{},D".format(NODE_ID, seq, read_flame()))

    healing = last_relay is not None and time.ticks_diff(now, last_relay) < RELAY_HOLD_MS
    led.value(1 if healing else 0)
