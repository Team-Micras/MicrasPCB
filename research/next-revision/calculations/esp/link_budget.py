#!/usr/bin/env python3
"""Wi-Fi link margin of main2's ESP32-S3-MINI-1 telemetry (boards/main2/Esp.zen).

The PCB antenna sits 2.2-3 mm over the maze floor and 4.4 mm from the USB-C shell; no published
measurement gives that detuning, so this sizes the margin it may consume.

Sources: ESP32-S3-MINI-1 & MINI-1U datasheet v1.7, Table 7-2 (TX power, typical) and Table 7-4
(RX sensitivity, typical); free-space path loss 20 log10(4 pi d / lambda). Antenna gains 0 dBi at
both ends (the module's PCB antenna and a laptop's are a few dBi; 0 dBi leaves that as margin).
The far end's receiver is taken as sensitive as the module's own.

Run: python3 research/next-revision/calculations/esp/link_budget.py
"""

import math

F = 2.44e9  # Hz, mid-band
C = 299_792_458.0
TX_DBM = 18.0  # the lowest 802.11g power in Table 7-2 (54 Mbit/s); 6 Mbit/s is 20.0 dBm
SENS = {"11g 6 Mbit/s": -93.0, "11g 12 Mbit/s": -90.8, "11g 24 Mbit/s": -85.5}  # Table 7-4
TELEMETRY = 2.0  # Mbit/s, the 256 kB/s stream (research H7 data link)

lam = C / F
for d in (1.0, 5.0, 20.0):
    fspl = 20 * math.log10(4 * math.pi * d / lam)
    rx = TX_DBM - fspl
    margins = ", ".join(f"{k} {rx - s:.1f} dB" for k, s in SENS.items())
    print(f"{d:4.0f} m: path loss {fspl:.1f} dB, received {rx:.1f} dBm; margin: {margins}")
print(f"the {TELEMETRY:g} Mbit/s telemetry fits a 6-12 Mbit/s rate with room for retries")
