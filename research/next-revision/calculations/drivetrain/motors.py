"""Motor data used by the simulations (every value from the cited datasheet; None = unknown)."""
# keys: R ohm (terminal, 25 C), kt Nm/A, J kg m^2 (rotor), L H, In A (max continuous), nmax rpm,
# Rth1 housing-ambient K/W, Rth2 winding-housing K/W, tw s (winding), tm s (motor), Tmax C, mass g
MOTORS = {
    # maxon catalogue Feb 2025 p98 (DCX 8 M, precious metal brushes)
    "DCX8M_4V2": dict(R=12.0, kt=3.36e-3, J=0.0379e-7, L=41.1e-6, In=0.199, nmax=17300,
                      Rth1=101, Rth2=16.9, tw=2.31, tm=162, Tmax=100, mass=4.4),
    "DCX8M_6V":  dict(R=29.0, kt=5.08e-3, J=0.0372e-7, L=94.1e-6, In=0.130, nmax=17300,
                      Rth1=101, Rth2=16.9, tw=2.31, tm=162, Tmax=100, mass=4.4),
    "DCX8M_12V": dict(R=92.2, kt=8.71e-3, J=0.035e-7, L=276e-6, In=0.0728, nmax=17300,
                      Rth1=101, Rth2=16.9, tw=2.31, tm=162, Tmax=100, mass=4.4),
    # maxon catalogue Apr 2022 p98 (DCX 12 L, precious metal brushes with CLL)
    "DCX12L_4V5": dict(R=1.94, kt=4.83e-3, J=0.533e-7, L=71e-6, In=0.851, nmax=12000,
                       Rth1=31, Rth2=10.3, tw=10.1, tm=194, Tmax=100, mass=16),
    # Micras v1 1020 coreless: firmware robot.hpp estimate (kt from back-EMF sweep, R estimate); thermal unknown
    "1020_v1": dict(R=15.4, kt=5.0e-3, J=None, L=None, In=None, nmax=None,
                    Rth1=None, Rth2=None, tw=None, tm=None, Tmax=None, mass=None),
}
# maxon catalogue Feb 2025 p100 (DCX 10 L, precious metal brushes)
MOTORS["DCX10L_4V5"] = dict(R=2.9, kt=3.52e-3, J=0.151e-7, L=45e-6, In=0.648, nmax=14300,
                            Rth1=36.5, Rth2=10.6, tw=3.94, tm=151, Tmax=100, mass=11)
MOTORS["DCX10L_6V"] = dict(R=6.4, kt=4.61e-3, J=0.119e-7, L=78e-6, In=0.436, nmax=14300,
                           Rth1=36.5, Rth2=10.6, tw=3.94, tm=151, Tmax=100, mass=11)
