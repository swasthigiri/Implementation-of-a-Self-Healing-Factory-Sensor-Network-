# LUMEN CORE - Node A (ESP32, DHT11 temperature on GPIO4)
# Save to the Node A ESP32 as main.py
#
# Packet: N<id>,<seq>,<value>,<D|R>,<pdr%>     (D = direct, R = relayed / self-healing)
# Backup (relay) neighbour: Node B
#
# RELAY SWITCH (demo): press the BOOT button (GPIO0) to break this node's direct link
# to the gateway; press again to restore it. PDR falls, node flips to relay (R) by itself,
# and returns to direct (D) as soon as a probe to the gateway is acknowledged again.

import network, espnow, time
from machine import Pin
import dht
import machine

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
try:
    sta.config(pm=network.WLAN.PM_NONE)   # no Wi-Fi power-save (also helps DHT timing)
except Exception:
    pass
print("This board MAC:", ":".join("{:02X}".format(b) for b in sta.config('mac')))

e = espnow.ESPNow()
e.active(True)

NODE_ID      = "A"
GATEWAY_MAC  = b'\xd4\xe9\xf4\xa3\xf1\x5c'   # Node G  D4:E9:F4:A3:F1:5C
NEIGHBOR_MAC = b'\xd4\xe9\xf4\xa4\x35\x70'   # Node B  D4:E9:F4:A4:35:70  (relay)
e.add_peer(GATEWAY_MAC)
e.add_peer(NEIGHBOR_MAC)

led = Pin(2, Pin.OUT)
Pin(4, Pin.IN, Pin.PULL_UP)
sensor = dht.DHT11(Pin(4))

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

# Forward packets from other nodes (B or C) to the gateway.
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
REPORT_S = 2

def pdr_ratio():
    return sum(window) / len(window) if window else 1.0

def record(ok):
    window.append(ok)
    if len(window) > WINDOW:
        window.pop(0)

def read_sensor():
    for attempt in range(5):
        state = machine.disable_irq()
        try:
            sensor.measure()
            machine.enable_irq(state)
            return sensor.temperature()
        except OSError:
            machine.enable_irq(state)
            time.sleep(2)
    return -1

seq = 0
shown_fault = False
while True:
    try:
        if fault != shown_fault:
            shown_fault = fault
            print(">>> FAULT", "ON  (direct link to gateway broken)" if fault else "OFF (direct link restored)")

        seq += 1
        val = read_sensor()
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
        time.sleep(REPORT_S)
    except Exception as err:
        print("loop error:", err)    # never let the main loop die
        time.sleep(1)
