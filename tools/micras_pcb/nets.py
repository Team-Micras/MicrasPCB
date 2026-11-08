"""The main board's nets by how they behave, for its routing (boards/main/layout/route.py) and its tests."""

from __future__ import annotations

# The DRV8874 bridges' Kelvin sense lines: each sits at its shunt's OUT1 end, so it swings 0-17 V
# at 100 kHz with OUT1 (SLVSF66A, PH/EN PWM), though it carries no current
KELVIN = {f"Motor_{s}_Sense{p}" for s in "LR" for p in "+-"}
# Nets whose voltage swings at the switching frequencies: the bridges' outputs (100 kHz PWM, with
# the shunts, the motor terminals and the Kelvin sense lines in series) and their charge pumps'
# flying capacitors (CPH, CPL: SLVSF66A 8.3.3), the fan driver's outputs, its low-side sources
# (LSS: the motor's pulsed return through R31), its bootstrap and charge-pump nodes (VBOOT, CP1,
# CP2: DS14341 Table 12), the buck's switch node and bootstrap (L6981 SW, BOOT) and the STM32
# SMPS's switch node, the buzzer's drain and the wall emitters' shared sink (175 mA pulses; each
# emitter's cathode and selector are on its wall board)
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
    "SENSORS.EMITTER_SINK",
}
# High-impedance or low-level analog nets into the ADCs and references: the phototransistors,
# the current amplifiers' outputs, the battery divider, the bridges' current references and the
# emitter sink's set point and feedback; and the analog rails (3V3_A: the INA241s, the
# phototransistors, the sink's op-amp; VDDA: the STM32's ADC reference)
ANALOG = {
    *(f"Wall_Sensor_{k}" for k in range(4)),
    "Current_Sensor_Right",
    "Current_Sensor_Left",
    "SENSORS.CURRENT_R_AMP",
    "SENSORS.CURRENT_L_AMP",
    "Battery_Voltage",
    "DRIVERS.MOTOR_R_VREF",
    "DRIVERS.MOTOR_L_VREF",
    "DRIVERS.MOTOR_R_IPROPI",
    "DRIVERS.MOTOR_L_IPROPI",
    "DRIVERS.FAN_REF",
    "SENSORS.SINK_SET",
    "SENSORS.SINK_FB",
    "Wall_Emitter_Set",
    "3V3_A",
    "VDDA",
}
# The battery-side supplies: the pack's current with the bridges' and the fan's PWM ripple on it
NOISY_SUPPLY = {"BAT_P", "GND_BAT", "VBAT", "VSYS", "5V_IN", "REGULATORS.LDO_IN"}
ANALOG_GAP = 0.5  # mm of copper-free gap, same layer (the ground planes shield one outer layer from the other)
# The STM32's and the ESP32's digital lines with fast edges or clocks: SPI's clock, the addressable
# LED's 800 kHz data, the encoders' quadrature and SPI lines, the ESP32-C5 link's clock and data, its
# USB pair (12 Mbit/s full speed, 4-20 ns edges, to the bare pads J3), and the PWM lines: the fan's 400 kHz (TIM14), the bridges' 100 kHz EN inputs (TIM1/TIM8) and the
# buzzer's gate drive (TIM17, its PWM at the buzzer's kHz tone with the MCU's fast edges)
FAST_DIGITAL = {
    "SPI_SCK",
    "LED_ARGB",
    "Fan_PWM",
    "Buzzer",
    "Motor_Right_EN",
    "Motor_Left_EN",
    *(f"Encoder_{s}_{n}" for s in ("Left", "Right") for n in ("ABI_A", "ABI_B", "CSn")),
    "ESP_SCK",
    "ESP_DATA",
    "ESP.ESP_SCK_IO",
    "ESP.ESP_DATA_IO",
    "ESP.USB_DN",
    "ESP.USB_DP",
}
# Their slow digital lines (control, status, interrupts, UART, SWD, SPI data and chip select,
# buttons and switches): an In2.Cu hop of one may run under another's B.Cu track for at most
# IN2_PARALLEL_MAX along each of its segments (the owner, 2026-10-24); every other B.Cu track
# crosses a hop square
SLOW_DIGITAL = {
    "Boot",
    "Button",
    "ESP.ESP_BOOT",
    "ESP.ESP_CSn_IO",
    "ESP.ESP_EN",
    "ESP.ESP_RXD0",
    "ESP.ESP_SWCLK",
    "ESP.ESP_TXD0",
    "ESP_CSn",
    "ESP_Flow",
    "Fan_Enable",
    "Fan_TOFF",
    "IMU_INT",
    "IMU_SPI_CSn",
    "LED_Blue",
    *(f"Motor_{s}_PH" for s in ("Left", "Right")),
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
