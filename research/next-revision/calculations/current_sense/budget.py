import math
VS=3.3; mid=VS/2
print("== Range table (VS=3.3 V, midscale, linear out 0.05..VS-0.2 V)")
for R in (0.005,0.010,0.020,0.040):
  for G in (10,20,50):
    k=R*G; ipos=(VS-0.2-mid)/k; ineg=(mid-0.05)/k
    lsb=VS/65536/k*1e3
    print(f"R={R*1e3:4.0f}mOhm G={G:3d} k={k:.3f}V/A +{ipos:5.2f}A/-{ineg:5.2f}A LSB16={lsb:.3f}mA P@3Arms={R*9*1e3:4.0f}mW P@{ipos:.1f}A={R*ipos**2:.2f}W")
print("\n== Current TSC2020 board: R=40m G=20, k=0.8")
k=0.8
print("lin range +-", (mid-0.1)/k, "A ; glitch 0.2V ->", 0.2/k*1e3,"mA")
for D in (0.1,0.3,0.5,0.7,0.9):
  ton=D*10
  print(f"D={D}: on {ton:.1f}us off {10-ton:.1f}us; clean (>3us after edge) on {max(0,ton-3):.1f}us off {max(0,10-ton-3):.1f}us")
# glitch average bias if one-sided: area 0.3V*2us per edge /10us
print("one-sided glitch 0.3V x 2us per edge, 1 edge/period bias:",0.3*2/10/k*1e3,"mA; 2 edges:",2*0.3*2/10/k*1e3,"mA")
print("\n== Ripple (sign-magnitude, slow decay, tau>>T): dIpp = V*D*(1-D)*T/L ; max at D=0.5 = V*T/(4L)")
for V in (16.8,20):
  for L in (20e-6,50e-6,100e-6,300e-6):
    print(f"V={V} L={L*1e6:.0f}uH f=100k: {V*1e-5/(4*L):.2f} App ; f=40k: {V*2.5e-5/(4*L):.2f} App")
print("\n== Error budget, proposal: 10 mOhm WSK2512 0.5%, INA241A2 (G=20), VS=VDDA=3.3V, 16-bit ADC")
k=0.2; dT=40
gain_terms={ # fraction
 'shunt tolerance (0.5%, removable by gain cal)':0.005,
 'shunt TCR 35ppm/K x 40K':35e-6*dT,
 'INA241A gain error max':0.0001,'INA241A gain drift 1ppm/K x40':1e-6*dT,
 'ADC gain error typ 15 LSB':15/65536,
}
rss=math.sqrt(sum(v*v for v in gain_terms.values()))
for n,v in gain_terms.items(): print(f"  gain: {n}: {v*100:.3f}%")
print(f"  gain RSS uncal {rss*100:.3f}% ; after gain cal (drop tolerance, keep 0.1% cal ref) {math.sqrt(rss**2-0.005**2+0.001**2)*100:.3f}%")
off={ # amps, residual after zero-cal at power-up
 'INA241A2 Vos drift 150nV/K x40K':150e-9*dT/0.01,
 'DC CMRR 150dB min x 20V':20*10**(-150/20)/0.01,
 'thermal EMF <3uV/K x 2K':3e-6*2/0.01,
 'ADC INL typ ~13 LSB':13*VS/65536/k,
}
for n,v in off.items(): print(f"  offset: {n}: {v*1e3:.2f} mA")
print(f"  offset RSS {math.sqrt(sum(v*v for v in off.values()))*1e3:.2f} mA")
# noise
en=49e-9; G=20; bw=1.1e6; enbw=bw*math.pi/2
amp_rms=en*G*math.sqrt(enbw)/k
adc_rms=(VS/(2*math.sqrt(2)))/10**(77/20)/k
print(f"  noise per single conversion: amp {amp_rms*1e3:.2f} mA rms (no RC), ADC {adc_rms*1e3:.2f} mA rms")
for n in (2,8,80):
  print(f"   averaged over {n} independent samples: {math.sqrt(amp_rms**2+adc_rms**2)/math.sqrt(n)*1e3:.2f} mA rms")
# with RC 220kHz output filter noise
fc=1/(2*math.pi*100*4.7e-9); print(f"  RC 100R/4.7nF fc={fc/1e3:.0f}kHz, amp noise {en*G*math.sqrt(fc*math.pi/2)/k*1e3:.2f} mA rms, group delay {1/(2*math.pi*fc)*1e6:.2f} us")
print("\n== Kelvin: shared copper Rcu in series with shunt gives gain error Rcu/Rshunt")
for Rcu in (0.1e-3,0.25e-3,0.5e-3):
  print(f"  Rcu={Rcu*1e3}mOhm: 40mOhm {Rcu/0.04*100:.2f}%  10mOhm {Rcu/0.01*100:.2f}%  5mOhm {Rcu/0.005*100:.2f}%")
print("\n== Kickback: 4pF CADC into C_filter")
for C in (1e-9,2.2e-9,4.7e-9):
  print(f"  C={C*1e9}nF: worst step 3.3V -> {3.3*4e-12/C*1e3:.2f} mV; same-channel (dV~50mV) {0.05*4e-12/C*1e6:.1f} uV")
print("\n== DRV8874 IPROPI: AERR <0.4A +-30mA, 0.4-1A 7.5%, 1-2 6%, 2-4 5.5%; RIPROPI for 3.0V at 4A:", 3.0/(4*450e-6),"Ohm")
print("== INA228 2 mOhm battery shunt: ADCRANGE=1 FS", 40.96e-3/0.002,"A, LSB", 78.125e-9/0.002*1e6,"uA; ADCRANGE=0 FS",163.84e-3/0.002,"A; offset 1uV ->",1e-6/0.002*1e3,"mA; P@10A",0.002*100,"W")
