"""main2's nets by how they behave, for its routing (boards/main2/layout/route.py) and its tests."""

from __future__ import annotations

# Nets whose voltage swings at the switching frequencies: the bridges' outputs (100 kHz PWM, with
# the shunts and motor terminals in series), the fan driver's output, the buck's and the STM32
# SMPS's switch nodes, the buzzer's drain and the wall emitters' cathodes (175 mA pulses)
SWITCHING = {
    *(f"DRIVERS.MOTOR_{s}_{n}" for s in "LR" for n in ("OUT1", "OUT2", "SHUNT", "TERMINAL")),
    "DRIVERS.FAN_OUT",
    "DRIVERS.FAN_MOTOR",
    "REGULATORS.BUCK_SW",
    "SMPS_LX",
    "PERIPHERALS.BUZZER_DRAIN",
    "PERIPHERALS.BUZZER_COIL",
    *(f"SENSORS.WALL{k}_LED_K" for k in range(4)),
    "SENSORS.EMITTER_SINK",
}
# High-impedance or low-level analog nets into the ADCs and references: the phototransistors,
# the current amplifiers' outputs, the battery divider, the bridges' current references and the
# emitter sink's set point and feedback
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
}
ANALOG_GAP = 0.5  # mm of copper-free gap, same layer (the ground planes shield one outer layer from the other)
