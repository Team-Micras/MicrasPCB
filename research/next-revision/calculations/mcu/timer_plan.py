#!/usr/bin/env python3
"""Timer register values for main2's firmware changes (boards/main2/firmware_changes.toml).

Clocks: the firmware's CubeMX project (MicrasFirmware cube/micras_v1.ioc, kept on main2):
SYSCLK 550 MHz, APB1 and APB2 137.5 MHz, so every timer kernel clock is 275 MHz
(RCC.Tim1OutputFreq_Value and Tim2OutputFreq_Value) and dac_pclk is APB1, 137.5 MHz.

1. WS2812C-2020-V6 on TIM17_CH1 (PB9): PWM period and the two compare values, each bit one PWM
   period, the next CCR1 written by DMA on tim17_up (DMAMUX1 input 112, RM0468 Table 118).
   Limits: T0H 220-380 ns, T1H 580-1000 ns, T0L and T1L 580-1000 ns, a bit (TDATA) >= 1.25 us,
   reset low >= 280 us (Worldsemi WS2812C-2020-V6 datasheet V1.1, p4 Data Transfer Time). The
   search maximises the smallest margin to any limit.
2. The motor PWM: TIM1 and TIM8 centre-aligned at 100 kHz.
3. The emitter DAC grid: a 50 us update of TIM4 (or TIM23) triggers DAC1 channel 2; a 20-entry
   circular DMA buffer holds one 1 ms frame (four 150 us pulses, 50 us gaps, a 200 us dark slot;
   MicrasFirmware config/targets/v1/target.hpp, wall_sensors_config).
4. The LED frame against that schedule: when it fits.

Run: python3 research/next-revision/calculations/mcu/timer_plan.py
"""

F_TIM = 275e6  # Hz, timer kernel clock
F_DAC_PCLK = 137.5e6  # Hz, APB1

# 1. WS2812C on TIM17.
T0H = (220e-9, 380e-9)
T1H = (580e-9, 1000e-9)
TXL = (580e-9, 1000e-9)  # T0L and T1L
TDATA_MIN = 1.25e-6  # T0H + T0L and T1H + T1L
RESET_MIN = 280e-6
LEDS = 2
best = None
for period in range(200, 600):  # ticks, PSC = 0
    for h0 in range(40, 160):
        for h1 in range(h0 + 1, 300):
            p, a, b = period / F_TIM, h0 / F_TIM, h1 / F_TIM
            margins = [
                a - T0H[0], T0H[1] - a,
                b - T1H[0], T1H[1] - b,
                (p - a) - TXL[0], TXL[1] - (p - a),
                (p - b) - TXL[0], TXL[1] - (p - b),
                p - TDATA_MIN,
            ]
            m = min(margins)
            if best is None or m > best[0]:
                best = (m, period, h0, h1)
m, period, h0, h1 = best
print("1. WS2812C-2020-V6 on TIM17_CH1, PSC = 0, timer clock 275 MHz")
print(f"   ARR = {period - 1} (period {period / F_TIM * 1e9:.1f} ns, {F_TIM / period / 1e3:.1f} kHz)")
print(f"   CCR1 = {h0} for a 0 (T0H {h0 / F_TIM * 1e9:.1f} ns, T0L {(period - h0) / F_TIM * 1e9:.1f} ns)")
print(f"   CCR1 = {h1} for a 1 (T1H {h1 / F_TIM * 1e9:.1f} ns, T1L {(period - h1) / F_TIM * 1e9:.1f} ns)")
print(f"   smallest margin to a datasheet limit: {m * 1e9:.1f} ns ({m * F_TIM:.0f} ticks)")
frame = 24 * LEDS * period / F_TIM
reset_periods = int(-(-RESET_MIN // (period / F_TIM)))
print(f"   {LEDS} LEDs x 24 bits: {frame * 1e6:.1f} us of data, then CCR1 = 0 for >= 280 us"
      f" ({reset_periods} periods, or stop the DMA with CCR1 = 0)")

# 2. Motor PWM.
F_PWM = 100e3
arr = round(F_TIM / (2 * F_PWM))
print("\n2. TIM1/TIM8 centre-aligned, PSC = 0")
print(f"   ARR = {arr}: {F_TIM / (2 * arr) / 1e3:.2f} kHz, one duty step = {1 / arr * 100:.3f} %"
      f" ({1 / F_TIM * 1e9:.2f} ns)")

# 3. Emitter DAC grid.
GRID = 50e-6
arr_dac = round(GRID * F_TIM) - 1
print("\n3. DAC1 channel 2 trigger timer (TIM4 or TIM23), PSC = 0")
print(f"   ARR = {arr_dac} ({(arr_dac + 1) / F_TIM * 1e6:.3f} us per trigger)")
slots = []
for k in range(4):
    slots += [f"c{k}", f"c{k}", f"c{k}", "0"]
slots += ["0", "0", "0", "0"]
print(f"   DMA buffer, one entry per 50 us, {len(slots)} entries per 1 ms frame: {', '.join(slots)}")
lag = 3 / F_DAC_PCLK + 4 / F_TIM  # DOR load 3 dac_pclk after the trigger (RM0468 31.4.7), resync
print(f"   DAC step after its grid edge: 3 dac_pclk (RM0468 31.4.7) + a few timer clocks of slave"
      f" resynchronisation, about {lag * 1e9:.0f} ns; the 5 us lead or trail Sensors.zen allows is"
      f" {5e-6 / lag:.0f} x that")

# 4. LED frame placement.
quiet = 141e-6  # selector rising edge to the end of its receiver scan
gap = 200e-6 - quiet
print("\n4. LED frame against the emitter schedule")
print(f"   free window after each lit slot's scan: {gap * 1e6:.0f} us; the dark slot: 200 us + {gap * 1e6:.0f} us")
print(f"   the {LEDS}-LED frame ({frame * 1e6:.1f} us) fits the dark slot"
      + (" and the gap" if frame < gap else ", not the gap after a lit slot"))
