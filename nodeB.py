# LUMEN CORE - Node B (ESP32, SW-420 vibration on GPIO34)
# Save to the Node B ESP32 as main.py
#
# Packet: N<id>,<seq>,<value>,<D|R>,<pdr%>     (D = direct, R = relayed / self-healing)
# Backup (relay) neighbour: Node C
#
# RELAY SWITCH (demo): press the BOOT button (GPIO0) to break this node's direct link
# to the gateway; press again to restore it. PDR falls, node flips to relay (R) by itself,
# and returns to direct (D) as soon as a probe to the gateway is acknowledged again.

import network, espnow, time
from machine import Pin

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
try:
    sta.config(pm=network.WLAN.PM_NONE)   # no Wi-Fi power-save
except Exception:
    pass
print("This board MAC:", ":".join("{:02X}".format(b) for b in sta.config('mac')))  # D4:E9:F4:A4:35:70

e = espnow.ESPNow()
e.active(True)

NODE_ID      = "B"
GATEWAY_MAC  = b'\xd4\xe9\xf4\xa3\xf1\x5c'   # Node G  D4:E9:F4:A3:F1:5C
NEIGHBOR_MAC = b'\xd4\xe9\xf4\xe2\xa4\x5c'   # Node C  D4:E9:F4:E2:A4:5C  (relay)
e.add_peer(GATEWAY_MAC)
e.add_peer(NEIGHBOR_MAC)

led = Pin(2, Pin.OUT)

# ---------------- relay switch: BOOT button (GPIO0) ----------------
btn = Pin(0, Pin.IN, Pin.PULL_UP)
fault = False
last_btn = time.ticks_ms()

def on_btn(p):
    global fault, last_btn
    now = time.ticks_ms()
    if time.ticks_diff(now, last_btn) > 300:      # debounce
        last_btn = now
        fault = not fault
btn.irq(trigger=Pin.IRQ_FALLING, handler=on_btn)
# --------------------------------------------------------------------

def send_to(mac, data):
    try:
        return e.send(mac, data, True)
    except OSError:
        return False

def send_gw(data):
    """Own direct send to the gateway; blocked while the demo fault is ON."""
    if fault:
        return False
    return send_to(GATEWAY_MAC, data)

# ---------------- SW-420 on GPIO34 ----------------
vib = Pin(34, Pin.IN)

REPORT_MS   = 500      # one report every 0.5 s -> dashboard reacts fast
SAMPLE_MS   = 1        # sample the pin every 1 ms (~500 samples per report)
MAX_LEVEL   = 1000
FULL_CHATTER_PER_S = 50                              # switch changes per second = max level
FULL_CHATTER = FULL_CHATTER_PER_S * REPORT_MS // 1000   # = 25 changes per 0.5 s window
SETTLE_MS   = 5000     # pin unchanged this long -> that level is the new "rest" level

# Initial guess of the rest level (keep sensor still for 1 s at power-on)
ones = 0
for _ in range(200):
    ones += vib.value()
    time.sleep_ms(5)
IDLE = 1 if ones > 100 else 0
last_change = time.ticks_ms()
print("SW-420 rest level:", IDLE)


def read_sensor():
    """Watch the pin for REPORT_MS and return a vibration level 0..1000.
       0         = still
       1..200    = light tap / small vibration
       200..600  = medium knocking
       600..1000 = strong / continuous shaking"""
    global IDLE, last_change
    changes = 0
    active = 0
    samples = 0
    last = vib.value()
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < REPORT_MS:
        v = vib.value()
        now = time.ticks_ms()
        if v != last:
            changes += 1
            last = v
            last_change = now
        elif time.ticks_diff(now, last_change) > SETTLE_MS and v != IDLE:
            IDLE = v                      # self-correct the rest level
            print("  rest level re-learned:", IDLE)
        if v != IDLE:
            active += 1
        samples += 1
        time.sleep_ms(SAMPLE_MS)

    active_pm = active * MAX_LEVEL // samples
    chatter = min(MAX_LEVEL, changes * MAX_LEVEL // FULL_CHATTER)
    level = (chatter * 6 + active_pm * 4) // 10   # blend: chatter weighted more
    level = max(level, active_pm)                 # held-on switch still counts fully
    if level > MAX_LEVEL:
        level = MAX_LEVEL
    if changes < 2 and active_pm < 20:            # ignore a single noise glitch
        level = 0
    print("  changes:", changes, " active:", active_pm, "/1000  chatter:", chatter, " -> level:", level)
    return level
# --------------------------------------------------

# Forward packets from other nodes (A or C) to the gateway.
# (The fault only breaks this node's OWN link, so forwarding keeps working.)
def on_recv(e):
    for host, msg in e:
        if msg and host != GATEWAY_MAC and msg[:1] == b'N':
            try:
                e.send(GATEWAY_MAC, msg, True)
            except OSError:
                pass
e.irq(on_recv)

WINDOW, THRESHOLD = 10, 0.7
window = []            # recent results of the DIRECT link to the gateway
use_relay = False

def pdr_ratio():
    return sum(window) / len(window) if window else 1.0

def record(ok):
    window.append(ok)
    if len(window) > WINDOW:
        window.pop(0)

seq = 0
shown_fault = False
while True:
    try:
        if fault != shown_fault:
            shown_fault = fault
            print(">>> FAULT", "ON  (direct link to gateway broken)" if fault else "OFF (direct link restored)")

        seq += 1
        val = read_sensor()          # takes 0.5 s - this is also the report delay
        route = "R" if use_relay else "D"
        pdr = int(pdr_ratio() * 100)
        packet = "N{},{},{},{},{}".format(NODE_ID, seq, val, route, pdr).encode()

        if use_relay:
            ok = send_to(NEIGHBOR_MAC, packet)          # data goes through the neighbour
            if send_gw(b'PROBE'):                       # is the direct link back?
                use_relay = False
                window[:] = [True]
            else:
                record(False)                           # direct link still bad
        else:
            ok = send_gw(packet)
            record(ok)
            if len(window) >= 5 and pdr_ratio() < THRESHOLD:
                use_relay = True

        print("Sent:", packet, "-> ack:", ok, " PDR:", int(pdr_ratio() * 100), "%  mode:", "RELAY" if use_relay else "DIRECT")
        led.value(1 if use_relay else 0)
    except Exception as err:
        print("loop error:", err)    # never let the main loop die
        time.sleep(1)
