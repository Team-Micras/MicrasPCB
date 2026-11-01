"""main2's nets by how they behave, for its routing (boards/main2/layout/route.py) and its tests."""

from __future__ import annotations

# The DRV8874 bridges' Kelvin sense lines: each sits at its shunt's OUT1 end, so it swings 0-17 V
# at 100 kHz with OUT1 (SLVSF66A, PH/EN PWM), though it carries no current
KELVIN = {f"Motor_{s}_Sense{p}" for s in "LR" for p in "+-"}
# Nets whose voltage swings at the switching frequencies: the bridges' outputs (100 kHz PWM, with
# the shunts, the motor terminals and the Kelvin sense lines in series) and their charge pumps'
# flying capacitors (CPH, CPL: SLVSF66A 8.3.3), the fan driver's outputs, its low-side sources
# (LSS: the motor's pulsed return through R31), its bootstrap and charge-pump nodes (VBOOT, CP1,
# CP2: DS14341 Table 12), the buck's switch node and bootstrap (L6981 SW, BOOT) and the STM32
# SMPS's switch node, the buzzer's drain and the wall emitters' cathodes (175 mA pulses)
SWITCHING = {
    *(f"DRIVERS.MOTOR_{s}_{n}" for s in "LR" for n in ("OUT1", "OUT2", "SHUNT", "TERMINAL", "CPH", "CPL")),
    *KELVIN,
    "DRIVERS.FAN_OUT",
    "DRIVERS.FAN_MOTOR",
    "DRIVERS.FAN_LSS",
    "DRIVERS.FAN_VBOOT",
    "DRIVERS.FAN_CP1",
    "DRIVERS.FAN_CP2",
    "REGULATORS.BUCK_SW",
    "REGULATORS.BUCK_BOOT",
    "SMPS_LX",
    "PERIPHERALS.BUZZER_DRAIN",
    "PERIPHERALS.BUZZER_COIL",
    *(f"SENSORS.WALL{k}_LED_K" for k in range(4)),
    "SENSORS.EMITTER_SINK",
}
# High-impedance or low-level analog nets into the ADCs and references: the phototransistors,
# the current amplifiers' outputs, the battery divider, the bridges' current references and the
# emitter sink's set point and feedback; and the analog rails (3V3_A: the INA241s, the
# phototransistors, the sink's op-amp; VDDA: the STM32's ADC reference)
ANALOG = {
    *(f"Wall_Sensor_{k}" for k in range(4)),
    "Current_Sensor_Left",
    "Current_Sensor_Right",
    "SENSORS.CURRENT_L_AMP",
    "SENSORS.CURRENT_R_AMP",
    "Battery_Voltage",
    "DRIVERS.MOTOR_L_VREF",
    "DRIVERS.MOTOR_R_VREF",
    "DRIVERS.MOTOR_L_IPROPI",
    "DRIVERS.MOTOR_R_IPROPI",
    "DRIVERS.FAN_REF",
    "SENSORS.SINK_SET",
    "SENSORS.SINK_FB",
    "Wall_Emitter_Set",
    "3V3_A",
    "VDDA",
}
ANALOG_GAP = 0.5  # mm of copper-free gap, same layer (the ground planes shield one outer layer from the other)
# The STM32's and the ESP32's digital lines with fast edges or clocks: SPI's clock, the addressable
# LED's 800 kHz data, the encoders' quadrature and SPI lines and the ESP32-C5 link's clock and data
FAST_DIGITAL = {
    "SPI_SCK",
    "LED_ARGB",
    *(f"Encoder_{s}_{n}" for s in ("Left", "Right") for n in ("ABI_A", "ABI_B", "CSn")),
    "ESP_SCK",
    "ESP_DATA",
    "ESP.ESP_SCK_IO",
    "ESP.ESP_DATA_IO",
}
# Their slow digital lines (control, status, interrupts, UART, SWD, SPI data and chip select,
# buttons and switches): an In2.Cu hop of one may run under another's B.Cu track for at most
# IN2_PARALLEL_MAX along each of its segments (the owner, 2026-10-24); every other B.Cu track
# crosses a hop square
SLOW_DIGITAL = {
    "Boot",
    "Button",
    "Buzzer",
    "ESP.ESP_BOOT",
    "ESP.ESP_CSn_IO",
    "ESP.ESP_EN",
    "ESP.ESP_RXD0",
    "ESP.ESP_SWCLK",
    "ESP.ESP_TXD0",
    "ESP_CSn",
    "ESP_Flow",
    "Fan_Enable",
    "Fan_PWM",
    "Fan_TOFF",
    "IMU_INT",
    "IMU_SPI_CSn",
    "LED_Red",
    *(f"Motor_{s}_{n}" for s in ("Left", "Right") for n in ("EN", "PH")),
    "Motors_Enable",
    "Motors_nFault",
    "Reset",
    "SPI_MISO",
    "SPI_MOSI",
    "SWCLK",
    "SWDIO",
    *(f"Switch_{k}" for k in range(4)),
    *(f"Wall_Sensor_PWM_{k}" for k in range(4)),
}
IN2_PARALLEL_MAX = 1.5  # mm (the longest run on the board is 1.0)
# Parts whose pins put a switching and an analog net side by side, so a track's escape stub (from a
# pin's centre) cannot keep ANALOG_GAP: the DRV8874s (VREF and IPROPI, pins 5-6, two pins from OUT1,
# pin 8: SLVSF66A pinout), the INA241s (Sense+ at pin 8 beside VS on 3V3_A, pin 7: SBOSA30D pinout)
# and the shunts whose sense pads the Kelvin lines leave (R65, R75)
STUB_PARTS = ("IC8", "IC9", "U10", "U11", "R65", "R75")
