#!/usr/bin/env python3
"""
Dead Giveaway - "Dead Man's Gulch" menu/lobby music.
Wistful frontier loop: fingerpicked guitar (Karplus-Strong), a lonesome whistle, a soft
shaker and brushed beat. Seamless (integer bars + wrapped voices/delay).

Output: western_loop.wav  (encode to mp3 after).
"""
import numpy as np, sys, wave

SR=44100; BPM=88.0
BEAT=60.0/BPM; BAR=BEAT*4; BARS=8
N=int(round(BAR*BARS*SR))          # ~21.8s
buf=np.zeros((N,2))
rng=np.random.default_rng(5)
def b2s(b): return int(round(b*BEAT*SR))

A4=440.0
_NM={'C':-9,'C#':-8,'D':-7,'D#':-6,'E':-5,'F':-4,'F#':-3,'G':-2,'G#':-1,'A':0,'A#':1,'B':2}
def nf(name): return A4*2**((_NM[name[:-1]]+(int(name[-1])-4)*12)/12.0)

def adsr(n,a,d,s,r):
    a,d,r=max(1,int(a*SR)),max(1,int(d*SR)),max(1,int(r*SR))
    if a+d+r>n: a=max(1,int(n*0.1)); d=max(1,int(n*0.2)); r=max(1,int(n*0.3))
    sl=max(0,n-a-d-r)
    e=np.concatenate([np.linspace(0,1,a,endpoint=False),np.linspace(1,s,d,endpoint=False),
                      np.full(sl,s),np.linspace(s,0,r)])
    return (e if len(e)>=n else np.pad(e,(0,n-len(e))))[:n]

def lp(x,cut):
    a=np.exp(-2*np.pi*cut/SR); b=1-a
    if a<=0: return x.copy()
    K=max(4,min(int(np.ceil(np.log(1e-4)/np.log(a))),8000))
    return np.convolve(x,b*(a**np.arange(K)))[:len(x)]
def hp(x,cut): return x-lp(x,cut)

def place(sig,pos,pan=0.0,gain=1.0):
    n=len(sig); idx=(pos+np.arange(n))%N
    gl=np.cos((pan+1)*np.pi/4)*gain; gr=np.sin((pan+1)*np.pi/4)*gain
    np.add.at(buf[:,0],idx,sig*gl); np.add.at(buf[:,1],idx,sig*gr)
def place_mono(arr,sig,pos):
    np.add.at(arr,(pos+np.arange(len(sig)))%N,sig)

def pingpong(mono,delay_beats,fb,taps):
    L=np.zeros(N); R=np.zeros(N); d=b2s(delay_beats); amp=1.0; left=True
    for k in range(taps):
        amp*=fb; rolled=np.roll(mono,((k+1)*d)%N)*amp
        if left: L+=rolled
        else: R+=rolled
        left=not left
    return L,R

# ---- Karplus-Strong plucked string (guitar) ----
def ks(freq, dur, decay=0.9965, amp=1.0, seed=0):
    n=int(dur*SR); p=max(2,int(round(SR/freq)))
    b=np.asarray(rng.standard_normal(p) if seed is None else
                 np.random.default_rng(seed).standard_normal(p), dtype=np.float64)
    out=np.empty(n); idx=0
    for i in range(n):
        cur=b[idx]; out[i]=cur
        nxt=b[idx+1] if idx+1<p else b[0]
        b[idx]=decay*0.5*(cur+nxt)
        idx+=1
        if idx==p: idx=0
    # gentle pick attack + natural fade tail
    out[:80]*=np.linspace(0,1,80)
    return out*amp

def whistle(freq, dur):
    n=int(dur*SR); t=np.arange(n)/SR
    vib=1+0.012*np.sin(2*np.pi*5.2*t)
    ph=2*np.pi*np.cumsum(freq*vib)/SR
    tone=np.sin(ph)+0.18*np.sin(2*ph)
    breath=hp(rng.standard_normal(n),4000)*0.04*np.exp(-t*3)
    env=adsr(n,0.05,0.15,0.7,0.25)
    return (tone*0.5+breath)*env

# 8-bar wistful frontier progression (i III VII VI ... V turn)
PROG=[('Am',['A2','A3','C4','E4']),('C',['C3','C4','E4','G4']),
      ('G', ['G2','G3','B3','D4']),('F',['F2','F3','A3','C4']),
      ('Am',['A2','A3','C4','E4']),('C',['C3','C4','E4','G4']),
      ('G', ['G2','G3','B3','D4']),('E',['E2','E3','G#3','B3'])]

# ---- fingerpicked guitar (Travis-ish): bass + alternating upper strings ----
gtr=np.zeros(N)
for bar,(nm,tones) in enumerate(PROG):
    base=bar*int(BAR*SR); root,s1,s2,s3=tones
    # eighth pattern: bass, hi, mid, hi, bass(5th-ish), hi, mid, hi
    seq=[(root,0.0),(s2,0.5),(s1,1.0),(s3,1.5),(root,2.0),(s2,2.5),(s1,3.0),(s3,3.5)]
    for note,beat in seq:
        f=nf(note); dur=0.6
        place_mono(gtr, ks(f,dur,decay=0.9968,amp=0.5,seed=int(f*10)+bar), base+b2s(beat))
gL,gR=pingpong(gtr,1.5,0.28,4)
place(gtr,0,gain=0.5); buf[:,0]+=gL*0.16; buf[:,1]+=gR*0.16

# ---- soft sustained reed pad (harmonica-ish) for warmth ----
def reed(freq,n):
    t=np.arange(n)/SR
    sig=0.5*np.sign(np.sin(2*np.pi*freq*t))+0.5*np.sin(2*np.pi*freq*t)
    sig=lp(sig,1600)
    return sig*adsr(n,0.3,0.3,0.8,0.5)
for bar,(nm,tones) in enumerate(PROG):
    base=bar*int(BAR*SR); n=int(BAR*SR)
    for ti,note in enumerate(tones[1:]):
        place(reed(nf(note),n),base,pan=-0.3+0.3*ti,gain=0.05)

# ---- lonesome whistle melody (sparse, over bars 2,4,6,8) ----
mel=np.zeros(N)
LINES={1:[('E5',0,1.0),('D5',1.0,1.0),('C5',2.0,2.0)],
       3:[('A4',0,1.5),('C5',1.5,2.5)],
       5:[('E5',0,1.0),('G5',1.0,1.0),('E5',2.0,1.0),('D5',3.0,1.0)],
       7:[('C5',0,1.5),('B4',1.5,1.0),('A4',2.5,1.5)]}
for bar,notes in LINES.items():
    base=bar*int(BAR*SR)
    for note,beat,dur in notes:
        place_mono(mel, whistle(nf(note), dur*BEAT), base+b2s(beat))
wL,wR=pingpong(mel,1.5,0.3,4)
place(mel,0,gain=0.5); buf[:,0]+=wL*0.18; buf[:,1]+=wR*0.18

# ---- light percussion: soft shaker on eighths + brushed beat + low stomp ----
def shaker():
    n=b2s(0.18); t=np.arange(n)/SR
    return hp(rng.standard_normal(n)*np.exp(-t*45),5000)
def stomp():
    n=b2s(0.4); t=np.arange(n)/SR; f=70+40*np.exp(-t*30)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*12)
def brush():
    n=b2s(0.3); t=np.arange(n)/SR
    return lp(rng.standard_normal(n)*np.exp(-t*16),3500)*0.7
for bar in range(BARS):
    base=bar*int(BAR*SR)
    place(stomp(),base+b2s(0),gain=0.5)
    place(stomp(),base+b2s(2),gain=0.4)
    place(brush(),base+b2s(2),gain=0.22)         # brushed backbeat on 3
    for e in range(8):
        place(shaker(),base+b2s(e*0.5),pan=0.12*(-1)**e,gain=0.07)

# ---- master ----
m=buf.copy(); m[:,0]=lp(m[:,0],13000); m[:,1]=lp(m[:,1],13000)
m=np.tanh(m*1.05); m=m/(np.max(np.abs(m)) or 1.0)*0.89
out=(np.clip(m,-1,1)*32767).astype(np.int16)
path=sys.argv[1] if len(sys.argv)>1 else "western_loop.wav"
with wave.open(path,'w') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())
seam=np.max(np.abs(m[0]-m[-1])); step=np.percentile(np.abs(np.diff(m,axis=0)),99)
print(f"wrote {path} dur={N/SR:.2f}s bars={BARS} bpm={BPM} seam={seam:.3f} 99p={step:.3f} {'SEAMLESS' if seam<step*3 else 'CHECK'}")
