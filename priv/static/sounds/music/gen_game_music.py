#!/usr/bin/env python3
"""
Dead Giveaway - in-game escalating music ("Neon Concourse").

4 additive intensity layers on a single 15.000s / 6-bar / 96 BPM / A-minor(phrygian) grid.
Cumulative stages s1..s4 get progressively more urgent; the game crossfades s(k)->s(k+1)
every 15s, then HOLDS / loops stage 4 (caps at ~1 min). Resets to s1 each new round.

Seamless by construction: integer bars + all voices and the wrapped ping-pong delay write
with modulo indices, so every stage loops without a click and shares the same phase grid
(so crossfades between stages line up).

Exports (WAV; encode to mp3 after):
  stage1.wav .. stage4.wav   cumulative loops the game plays
  stem0.wav  .. stem3.wav    individual layers (for a future WebAudio live mix)
  demo.wav                   s1..s4 concatenated = 60s play-through of the whole build
"""
import numpy as np, sys, wave, os

SR=44100; BPM=128.0
BEAT=60.0/BPM; BAR=BEAT*4; BARS=8
N=int(round(BAR*BARS*SR))            # 15.000s exactly (128 BPM -> 8 bars)
rng=np.random.default_rng(11)

def b2s(beats): return int(round(beats*BEAT*SR))

A4=440.0
_NM={'C':-9,'C#':-8,'D':-7,'D#':-6,'E':-5,'F':-4,'F#':-3,'G':-2,'G#':-1,'A':0,'A#':1,'B':2}
def nf(name): return A4*2**((_NM[name[:-1]]+(int(name[-1])-4)*12)/12.0)

def adsr(n,a,d,s,r):
    a,d,r=max(1,int(a*SR)),max(1,int(d*SR)),max(1,int(r*SR))
    if a+d+r>n: a=max(1,int(n*0.1)); d=max(1,int(n*0.2)); r=max(1,int(n*0.3))
    sl=max(0,n-a-d-r)
    env=np.concatenate([np.linspace(0,1,a,endpoint=False),np.linspace(1,s,d,endpoint=False),
                        np.full(sl,s),np.linspace(s,0,r)])
    if len(env)<n: env=np.pad(env,(0,n-len(env)))
    return env[:n]

def lp(x,cut):
    a=np.exp(-2*np.pi*cut/SR); b=1-a
    if a<=0: return x.copy()
    K=max(4,min(int(np.ceil(np.log(1e-4)/np.log(a))),8000))
    return np.convolve(x,b*(a**np.arange(K)))[:len(x)]
def hp(x,cut): return x-lp(x,cut)

def osc(freq,n,wave='saw',detune=0.0):
    t=np.arange(n)/SR; f=freq*2**(detune/1200.0); ph=f*t
    if wave=='sine': return np.sin(2*np.pi*ph)
    if wave=='tri':  return 2*np.abs(2*(ph-np.floor(ph+0.5)))-1
    if wave=='square': return np.sign(np.sin(2*np.pi*ph))
    return 2*(ph-np.floor(ph+0.5))

def place(buf,sig,pos,pan=0.0,gain=1.0):
    n=len(sig); idx=(pos+np.arange(n))%N
    gl=np.cos((pan+1)*np.pi/4)*gain; gr=np.sin((pan+1)*np.pi/4)*gain
    np.add.at(buf[:,0],idx,sig*gl); np.add.at(buf[:,1],idx,sig*gr)
def place_mono(arr,sig,pos):
    n=len(sig); np.add.at(arr,(pos+np.arange(n))%N,sig)

def pingpong(mono,delay_beats,fb,taps):
    L=np.zeros(N); R=np.zeros(N); d=b2s(delay_beats); amp=1.0; left=True
    for k in range(taps):
        amp*=fb; rolled=np.roll(mono,((k+1)*d)%N)*amp
        if left: L+=rolled
        else: R+=rolled
        left=not left
    return L,R

# 8-bar loop: A-minor with phrygian bII (Bb) + dominant E turnaround back to Am
PROG=[('Am',['A3','C4','E4'],'A1'),
      ('F', ['A3','C4','F4'],'F1'),
      ('G', ['G3','B3','D4'],'G1'),
      ('Am',['A3','C4','E4'],'A1'),
      ('F', ['A3','C4','F4'],'F1'),
      ('Bb',['A#3','D4','F4'],'A#1'),   # Bb=A#
      ('E', ['G#3','B3','E4'],'E1'),
      ('E', ['G#3','B3','E4'],'E1')]

# ---- percussion voices ----
def _kick(nb=0.5):
    n=b2s(nb); t=np.arange(n)/SR; f=52+80*np.exp(-t*32)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*9)
def _clap(nb=0.4):
    n=b2s(nb); t=np.arange(n)/SR
    return lp(rng.standard_normal(n)*np.exp(-t*26),6500)*0.9
def _hat(nb=0.1):
    n=b2s(nb); t=np.arange(n)/SR
    return hp(rng.standard_normal(n)*np.exp(-t*55),7000)
def _rim(nb=0.1):
    n=b2s(nb); t=np.arange(n)/SR
    return np.sin(2*np.pi*1700*t)*np.exp(-t*120)*0.8
def _ride(nb=0.2):
    n=b2s(nb); t=np.arange(n)/SR
    return hp(rng.standard_normal(n)*np.exp(-t*22),9000)*0.6
def _tom(freq,nb=0.3):
    n=b2s(nb); t=np.arange(n)/SR; f=freq*np.exp(-t*4)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*12)

# ---- reworked synth bass: punchy, defined, with octave/fifth movement ----
def _bassvoice(f,nb):
    n=b2s(nb); env=adsr(n,0.004,0.09,0.5,0.08)
    body=osc(f,n,'sine')+0.45*osc(f,n,'saw')+0.18*osc(f*2,n,'saw')   # sub + grit + definition
    return np.tanh(lp(body,1500)*env*1.05)

def _bassline(buf,gain):
    # eighth-note groove, root in bass register with octave/fifth pops for movement
    offs=[0,0,12,0,0,0,7,12]                       # semitone offset per eighth slot
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); rf=nf(root)*2        # up an octave into the bass register
        for e in range(8):
            f=rf*2**(offs[e]/12.0)
            place(buf,_bassvoice(f,0.46),base+b2s(e*0.5),gain=gain)

# ============================================================================
# LAYERS
# ============================================================================
def L0_bed():
    # Stage 1: warm pad + reworked groovy bass + a LIGHT groove (beat from the start).
    buf=np.zeros((N,2))
    # warm pad
    for bar,(nm,tones,root) in enumerate(PROG):
        pos=bar*int(BAR*SR); n=int(BAR*SR); env=adsr(n,0.4,0.4,0.85,0.5)
        for ti,t in enumerate(tones):
            f=nf(t); v=(osc(f,n,'saw',-6)+osc(f,n,'saw',6)+0.6*osc(f,n,'saw'))/2.6
            place(buf,lp(v,1300)*env,pos,pan=-0.35+0.35*ti,gain=0.11)
    # sustained sub root for low-end glue (under the moving bassline)
    for bar,(nm,tones,root) in enumerate(PROG):
        pos=bar*int(BAR*SR); n=b2s(3.6); env=adsr(n,0.02,0.3,0.8,0.6)
        f=nf(root); place(buf,(osc(f,n,'sine')+0.25*osc(f,n,'tri'))*env,pos,gain=0.26)
    # reworked groovy bassline (present from stage 1)
    _bassline(buf,gain=0.34)
    # light groove: kick on 1 & 3, soft backbeat on 2 & 4, soft 8th hats
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        place(buf,_kick(),base+b2s(0),gain=0.9)
        place(buf,_kick(),base+b2s(2),gain=0.7)
        place(buf,_clap(),base+b2s(1),gain=0.26)
        place(buf,_clap(),base+b2s(3),gain=0.26)
        for e in range(8):
            place(buf,_hat(0.10),base+b2s(e*0.5),pan=0.10*(-1)**e,gain=0.10)
    return buf

def L1_tense():
    # Stage 2: tighten the groove + bring in the arp (bass already grooves from stage 1).
    buf=np.zeros((N,2))
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        place(buf,_rim(),base+b2s(2),gain=0.22)               # rim accent on 3
        place(buf,_kick(0.4),base+b2s(2.75),gain=0.40)        # syncopated pickup (and of 3)
        for e in (1,3,5,7):                                   # offbeat hat accents
            place(buf,_hat(0.14),base+b2s(e*0.5),pan=0.12*(-1)**e,gain=0.10)
    # mid arp eighths + ping-pong
    arp=np.zeros(N)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); pat=[tones[0],tones[2],tones[1],tones[2]]*2
        for i,t in enumerate(pat):
            f=nf(t)*2; n=b2s(0.5); env=adsr(n,0.005,0.1,0.0,0.05)
            place_mono(arp,(osc(f,n,'tri')+0.2*osc(f,n,'sine'))*env,base+b2s(i*0.5))
    dL,dR=pingpong(arp,0.75,0.4,6)
    place(buf,arp,0,gain=0.08); buf[:,0]+=dL*0.09; buf[:,1]+=dR*0.09
    return buf

def L2_urgent():
    # Stage 3: fill kicks to four-on-the-floor + harder backbeat + reinforced hats.
    buf=np.zeros((N,2))
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        for beat in (1,3): place(buf,_kick(),base+b2s(beat),gain=0.8)   # adds 2&4 -> 4-on-floor
        for beat in (1,3): place(buf,_clap(),base+b2s(beat),gain=0.42)  # harder backbeat
        for e in range(8): place(buf,_hat(0.10),base+b2s(e*0.5),pan=0.12*(-1)**e,gain=0.10)
    return buf

def L3_frantic():
    buf=np.zeros((N,2))
    # 16th hats
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        for s in range(16):
            place(buf,_hat(0.05),base+b2s(s*0.25),pan=0.18*(-1)**s,gain=0.12 if s%2 else 0.15)
    # tense phrygian counter stabs
    hi=np.zeros(N)
    for bar,note in [(0,'A5'),(2,'G5'),(4,'A5'),(5,'A#5'),(6,'G#5'),(7,'E5')]:
        f=nf(note); n=b2s(0.6); env=adsr(n,0.005,0.15,0.2,0.2)
        place_mono(hi,lp((osc(f,n,'saw',7)+osc(f,n,'saw',-7))*0.5,3000)*env,int(bar*BAR*SR))
    hL,hR=pingpong(hi,0.5,0.35,6)
    place(buf,hi,0,gain=0.10); buf[:,0]+=hL*0.08; buf[:,1]+=hR*0.08
    # 16th arp
    arp=np.zeros(N)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); seq=[tones[0],tones[1],tones[2],tones[1]]*4
        for i,t in enumerate(seq):
            f=nf(t)*2; n=b2s(0.25); env=adsr(n,0.003,0.06,0.0,0.03)
            place_mono(arp,(osc(f,n,'square')*0.4+osc(f,n,'tri')*0.6)*env,base+b2s(i*0.25))
    aL,aR=pingpong(arp,0.375,0.35,6)
    place(buf,np.tanh(arp*1.5),0,gain=0.06); buf[:,0]+=aL*0.05; buf[:,1]+=aR*0.05
    # lead stabs on the Bb/E turnaround
    for bar,note in [(5,'A#4'),(6,'G#4'),(7,'E4')]:
        f=nf(note); n=b2s(1.4); env=adsr(n,0.01,0.2,0.5,0.3)
        sig=(osc(f,n,'saw',12)+osc(f,n,'saw',-12)+osc(f,n,'square'))/2.4
        place(buf,np.tanh(lp(sig,2600)*env*1.4),int(bar*BAR*SR),gain=0.12)
    # ride eighths
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        for e in range(8): place(buf,_ride(),base+b2s(e*0.5),pan=0.2,gain=0.06)
    # noise riser over last 2 bars (wraps into the loop -> tension resolves at restart)
    start=int((BARS-2)*BAR*SR); n=N-start; t=np.arange(n)/SR; dur=n/SR
    ris=hp(rng.standard_normal(n),500)*((t/dur)**2)*0.5
    place(buf,ris*0.16,start)
    # tom fill into the loop point (last beat of the final bar)
    for i,off in enumerate([0,0.25,0.5,0.75]):
        place(buf,_tom(180-i*18),int((BARS-1)*BAR*SR)+b2s(3+off),gain=0.4)
    return np.tanh(buf*1.12)

# ============================================================================
def master(buf,target_peak=0.89):
    m=buf.copy(); m[:,0]=lp(m[:,0],14000); m[:,1]=lp(m[:,1],14000)
    m=np.tanh(m*1.05); pk=np.max(np.abs(m)) or 1.0
    return m/pk*target_peak

def write_wav(path,stereo):
    out=(np.clip(stereo,-1,1)*32767).astype(np.int16)
    with wave.open(path,'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())

def main():
    outdir=sys.argv[1] if len(sys.argv)>1 else "."
    os.makedirs(outdir,exist_ok=True)
    print("rendering layers...")
    layers=[L0_bed(),L1_tense(),L2_urgent(),L3_frantic()]
    for i,ly in enumerate(layers): write_wav(os.path.join(outdir,f"stem{i}.wav"),master(ly,0.8))
    acc=np.zeros((N,2)); rms=[]; demo=[]
    for i,ly in enumerate(layers):
        acc=acc+ly; st=master(acc)
        write_wav(os.path.join(outdir,f"stage{i+1}.wav"),st)
        rms.append(np.sqrt(np.mean(st**2))); demo.append(st)
    write_wav(os.path.join(outdir,"demo.wav"),np.concatenate(demo,axis=0))
    print("loop len: %.3fs  bars=%d  bpm=%g"%(N/SR,BARS,BPM))
    print("stage RMS (rises with urgency): "+"  ".join("s%d=%.3f"%(i+1,r) for i,r in enumerate(rms)))
    print("done ->",outdir)

if __name__=="__main__":
    main()
