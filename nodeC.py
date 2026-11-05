# LUMEN CORE - Node C (ESP32, MQ-2 gas/smoke sensor)   MAC: D4:E9:F4:E2:A4:5C
# Save to the Node C ESP32 as main.py
#
# Wiring:
#   MQ-2 A0  -> GPIO32 (ADC1_CH4)
#   MQ-2 D0  -> GPIO35 (input-only)
#   MQ-2 GND -> ESP32 GND
#   MQ-2 VCC -> 5V for a proper heater (see NOTE below)
#   Onboard LED GPIO2 = relay indicator (ON while self-healing via neighbour)
#
# NOTE: if the MQ-2 module is powered from 5V, its A0 can swing above 3.3V.
#       Put a voltage divider (e.g. 10k + 20k) between A0 and GPIO32 so the
#       ESP32 pin is never driven above 3.3V.
#
# Packet: N<id>,<seq>,<value>,<D|R>,<pdr%>     (D = direct, R = relayed / self-healing)
# Example: NC,12,347,D,100
# Backup (relay) neighbour: Node B
#
# RELAY SWITCH (demo): press the BOOT button (GPIO0) to break this node's direct link
# to the gateway; press again to restore it. PDR falls, node flips to relay (R) by itself,
# and returns to direct (D) as soon as a probe to the gateway is acknowledged again.
#
# Mesh path:  Node A/B/C --ESP-NOW--> Node G --UART--> STM32 --USB--> PC dashboard

import network, espnow, time
from machine import Pin, ADC

# ---------------- radio: station mode, not connected to any AP ----------------
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
try:
    sta.config(pm=network.WLAN.PM_NONE)   # no Wi-Fi power-save: don't miss packets
except Exception:
    pass
print("This board MAC:", ":".join("{:02X}".format(b) for b in sta.config('mac')))  # D4:E9:F4:E2:A4:5C

e = espnow.ESPNow()
e.active(True)

NODE_ID      = "C"
GATEWAY_MAC  = b'\xd4\xe9\xf4\xa3\xf1\x5c'   # Node G  D4:E9:F4:A3:F1:5C
NEIGHBOR_MAC = b'\xd4\xe9\xf4\xa4\x35\x70'   # Node B  D4:E9:F4:A4:35:70  (relay)
e.add_peer(GATEWAY_MAC)
e.add_peer(NEIGHBOR_MAC)

led = Pin(2, Pin.OUT)
led.value(0)

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

# Forward packets from other nodes (A or B) to the gateway.
# (The fault only breaks this node's OWN link, so forwarding keeps working.)
def on_recv(e):
    for host, msg in e:
        if msg and host != GATEWAY_MAC and msg[:1] == b'N':
            try:
                e.send(GATEWAY_MAC, msg, True)
            except OSError:
                pass
e.irq(on_recv)

# ---------------- MQ-2 on GPIO32 (analog) / GPIO35 (digital) ----------------
adc = ADC(Pin(32))
adc.atten(ADC.ATTN_11DB)              # full 0..3.3 V range
try:
    adc.width(ADC.WIDTH_12BIT)        # 0..4095
except Exception:
    pass
gas_do = Pin(35, Pin.IN)              # LOW = gas above the module's potentiometer threshold

SAMPLES = 32
MAX_LEVEL = 1000
FULL_SCALE_MV = 3300      # level 1000 = 3.3 V at GPIO32
DO_ALARM_LEVEL = 800      # when the module's D0 trips (LOW) the level is at least this
zero_count = 0

def read_mv():
    """One reading in millivolts. read_uv() is factory-calibrated and far better than
    read() near 0 V, where the raw ESP32 ADC is dead (reads 0 below ~100 mV)."""
    try:
        return adc.read_uv() // 1000
    except Exception:
        return adc.read() * FULL_SCALE_MV // 4095

def read_sensor():
    """Average 32 samples (~160 ms) and scale to a gas level 0..1000."""
    global zero_count
    total = 0
    for _ in range(SAMPLES):
        total += read_mv()
        time.sleep_ms(5)
    mv = total // SAMPLES
    level = mv * MAX_LEVEL // FULL_SCALE_MV

    do_alarm = (gas_do.value() == 0)          # most MQ-2 modules pull D0 LOW on gas
    if do_alarm and level < DO_ALARM_LEVEL:
        level = DO_ALARM_LEVEL
    if level > MAX_LEVEL:
        level = MAX_LEVEL

    if mv < 5:                                # pin is at ~0 V: wiring / power problem
        zero_count += 1
        if zero_count == 5:
            print("  !!! A0 reads 0 V - check A0->GPIO32, GND, and MQ-2 VCC")
    else:
        zero_count = 0

    print("  MQ-2 pin:", mv, "mV  level:", level, "/1000  DO:", gas_do.value())
    return level
# ---------------------------------------------------------------------------

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

# MQ-2 heater warm-up: discard the first readings (forwarding keeps working via irq).
# A real MQ-2 needs minutes to fully stabilise; this is only a short demo warm-up.
print("MQ-2 warming up...")
for _ in range(5):
    adc.read()
    time.sleep(1)
print("Node C ready")

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