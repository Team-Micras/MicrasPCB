#!/usr/bin/env python3
"""Wi-Fi link margin of main2's ESP32-C5-MINI-1 telemetry at 5 GHz (boards/main2/Esp.zen).

The PCB antenna sits 2.2-3 mm over the maze floor; no published measurement gives that detuning,
so this sizes the margin it may consume.

Sources: ESP32-C5-MINI-1 & MINI-1U datasheet v1.4, Table 7-8 (5 GHz TX power, typical) and Table
7-10 (5 GHz RX sensitivity, typical); free-space path loss 20 log10(4 pi d / lambda) at the top of
the band the module covers (5180-5885 MHz, Table 7-7; 5.825 GHz, channel 165, taken as the worst
case of the channels the robot uses). Antenna gains 0 dBi at both ends (the module's PCB antenna
and a laptop's are a few dBi; 0 dBi leaves that as margin). The far end's receiver is taken as
sensitive as the module's own.

Run: python3 research/next-revision/calculations/esp/link_budget.py
"""

import math

F = 5.825e9  # Hz
C = 299_792_458.0
TX_DBM = 15.5  # the lowest 802.11a power in Table 7-8 (54 Mbit/s); 6 Mbit/s is 16.5 dBm
SENS = {"11a 6 Mbit/s": -92.5, "11a 12 Mbit/s": -90.5, "11a 24 Mbit/s": -85.5}  # Table 7-10
TELEMETRY = 2.0  # Mbit/s, the 256 kB/s stream (research H7 data link)

lam = C / F
for d in (1.0, 5.0, 20.0):
    fspl = 20 * math.log10(4 * math.pi * d / lam)
    rx = TX_DBM - fspl
    margins = ", ".join(f"{k} {rx - s:.1f} dB" for k, s in SENS.items())
    print(f"{d:4.0f} m: path loss {fspl:.1f} dB, received {rx:.1f} dBm; margin: {margins}")
print(f"the {TELEMETRY:g} Mbit/s telemetry fits a 6-12 Mbit/s rate with room for retries")
