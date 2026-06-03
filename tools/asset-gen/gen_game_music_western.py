#!/usr/bin/env python3
"""
Dead Giveaway - Western in-round escalating music ("Dead Man's Gulch").

Same architecture as the neon game music: 4 additive layers on a 15.000s / 8-bar / 128 BPM
/ A-minor(phrygian) grid. Cumulative stages s1..s4 get more urgent; the game crossfades
s(k)->s(k+1) every 15s, then holds at stage 4. Seamless (integer bars + wrapped voices/delay).

Western voices: Karplus-Strong plucked guitar (bass, strum, arp, frantic banjo), boot-stomp
"kick", handclaps, tambourine/shaker, woodblock, and a lonesome-to-feral whistle lead.

Exports: stage1..4.wav, stem0..3.wav, demo.wav  (encode to mp3 after).
"""
import numpy as np, sys, wave, os

SR=44100; BPM=128.0
BEAT=60.0/BPM; BAR=BEAT*4; BARS=8
N=int(round(BAR*BARS*SR))          # 15.000s
rng=np.random.default_rng(13)
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

def place(buf,sig,pos,pan=0.0,gain=1.0):
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

# ---- Karplus-Strong plucked string ----
def ks(freq,dur,decay=0.9965,amp=1.0,seed=0,bright=0.5):
    n=int(dur*SR); p=max(2,int(round(SR/freq)))
    b=np.array(np.random.default_rng(seed).standard_normal(p),dtype=np.float64)
    out=np.empty(n); idx=0
    for i in range(n):
        cur=b[idx]; out[i]=cur
        nxt=b[idx+1] if idx+1<p else b[0]
        b[idx]=decay*(bright*cur+(1-bright)*nxt)
        idx+=1
        if idx==p: idx=0
    out[:60]*=np.linspace(0,1,60)
    return out*amp

def strum(tones,dur,amp,seed):
    sig=np.zeros(int(dur*SR))
    for j,t in enumerate(tones):
        s=ks(nf(t),dur,decay=0.992,amp=amp,seed=seed+j)
        off=int(j*0.012*SR)
        if off<len(sig): sig[off:]+=s[:len(sig)-off]
    return sig

def whistle(freq,dur,vibd=0.012):
    n=int(dur*SR); t=np.arange(n)/SR
    vib=1+vibd*np.sin(2*np.pi*5.4*t)
    ph=2*np.pi*np.cumsum(freq*vib)/SR
    tone=np.sin(ph)+0.2*np.sin(2*ph)
    breath=hp(rng.standard_normal(n),4000)*0.04*np.exp(-t*3)
    return (tone*0.5+breath)*adsr(n,0.04,0.12,0.7,0.2)

# ---- percussion ----
def stomp(nb=0.5):
    n=b2s(nb); t=np.arange(n)/SR; f=64+60*np.exp(-t*30)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*11)
def clap(nb=0.35):
    n=b2s(nb); t=np.arange(n)/SR
    return lp(rng.standard_normal(n)*np.exp(-t*24),5500)*0.9
def shaker(nb=0.14):
    n=b2s(nb); t=np.arange(n)/SR
    return hp(rng.standard_normal(n)*np.exp(-t*50),5500)
def tamb(nb=0.18):
    n=b2s(nb); t=np.arange(n)/SR
    jingle=hp(rng.standard_normal(n)*np.exp(-t*30),7000)
    ring=np.sin(2*np.pi*5200*t)*np.exp(-t*40)*0.3
    return jingle+ring
def wood(nb=0.1):
    n=b2s(nb); t=np.arange(n)/SR
    return np.sin(2*np.pi*1100*t)*np.exp(-t*90)*0.9
def tom(freq,nb=0.3):
    n=b2s(nb); t=np.arange(n)/SR; f=freq*np.exp(-t*4)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*12)

PROG=[('Am',['A3','C4','E4'],'A1'),('F',['A3','C4','F4'],'F1'),
      ('G', ['G3','B3','D4'],'G1'),('Am',['A3','C4','E4'],'A1'),
      ('F', ['A3','C4','F4'],'F1'),('Bb',['A#3','D4','F4'],'A#1'),
      ('E', ['G#3','B3','E4'],'E1'),('E',['G#3','B3','E4'],'E1')]

# ============================================================================
def L0_bed():
    buf=np.zeros((N,2))
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); n=int(BAR*SR); t=np.arange(n)/SR
        for ti,tn in enumerate(tones):
            f=nf(tn); sig=lp(0.5*np.sign(np.sin(2*np.pi*f*t))+0.5*np.sin(2*np.pi*f*t),1500)
            place(buf,sig*adsr(n,0.25,0.3,0.8,0.4),base,pan=-0.3+0.3*ti,gain=0.045)
    offs=[0,0,12,0,0,0,7,12]
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); rf=nf(root)*2
        for e in range(8):
            f=rf*2**(offs[e]/12.0)
            place(buf,ks(f,0.46,decay=0.994,amp=0.6,seed=int(f)+e),base+b2s(e*0.5),gain=0.34)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR)
        place(buf,stomp(),base+b2s(0),gain=0.9)
        place(buf,stomp(),base+b2s(2),gain=0.7)
        place(buf,strum(tones,0.4,0.3,seed=bar*7),base+b2s(1),pan=-0.1,gain=0.28)
        place(buf,strum(tones,0.4,0.3,seed=bar*7+3),base+b2s(3),pan=0.1,gain=0.28)
        place(buf,clap(),base+b2s(1),gain=0.22); place(buf,clap(),base+b2s(3),gain=0.22)
        for e in range(8): place(buf,shaker(),base+b2s(e*0.5),pan=0.1*(-1)**e,gain=0.08)
    return buf

def L1_tense():
    buf=np.zeros((N,2))
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        place(buf,wood(),base+b2s(2),gain=0.3)
        place(buf,stomp(0.4),base+b2s(2.75),gain=0.4)
        for e in (1,3,5,7): place(buf,tamb(),base+b2s(e*0.5),pan=0.12*(-1)**e,gain=0.12)
    arp=np.zeros(N)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); pat=[tones[0],tones[2],tones[1],tones[2]]*2
        for i,tn in enumerate(pat):
            f=nf(tn)*2
            place_mono(arp,ks(f,0.5,decay=0.992,amp=0.5,seed=int(f)+i+bar),base+b2s(i*0.5))
    dL,dR=pingpong(arp,0.75,0.32,5)
    place(buf,arp,0,gain=0.12); buf[:,0]+=dL*0.10; buf[:,1]+=dR*0.10
    mel=np.zeros(N)
    for bar,note in [(2,'E5'),(5,'A5'),(7,'G5')]:
        place_mono(mel,whistle(nf(note),0.9*BEAT),int(bar*BAR*SR))
    wL,wR=pingpong(mel,0.75,0.3,4)
    place(buf,mel,0,gain=0.16); buf[:,0]+=wL*0.10; buf[:,1]+=wR*0.10
    return buf

def L2_urgent():
    buf=np.zeros((N,2))
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR)
        for beat in (1,3): place(buf,stomp(),base+b2s(beat),gain=0.8)
        for beat in (1,3): place(buf,clap(),base+b2s(beat),gain=0.42)
        for e in range(16): place(buf,shaker(0.1),base+b2s(e*0.25),pan=0.12*(-1)**e,gain=0.07)
    bj=np.zeros(N)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR)
        for e in range(8):
            f=nf(tones[2])*2
            place_mono(bj,ks(f,0.26,decay=0.985,amp=0.4,seed=int(f)+e+bar,bright=0.45),base+b2s(e*0.5))
    place(buf,bj,0,pan=0.15,gain=0.10)
    return buf

def L3_frantic():
    buf=np.zeros((N,2))
    for bar in range(BARS):
        base=bar*int(BAR*SR)
        for s in range(16):
            place(buf,tamb(0.06),base+b2s(s*0.25),pan=0.18*(-1)**s,gain=0.10 if s%2 else 0.13)
    roll=np.zeros(N)
    for bar,(nm,tones,root) in enumerate(PROG):
        base=bar*int(BAR*SR); seq=[tones[0],tones[1],tones[2],tones[1]]*4
        for i,tn in enumerate(seq):
            f=nf(tn)*2
            place_mono(roll,ks(f,0.16,decay=0.975,amp=0.4,seed=int(f)+i+bar,bright=0.4),base+b2s(i*0.25))
    rL,rR=pingpong(roll,0.375,0.3,5)
    place(buf,np.tanh(roll*1.3),0,gain=0.08); buf[:,0]+=rL*0.05; buf[:,1]+=rR*0.05
    mel=np.zeros(N)
    for bar,note,dur in [(5,'A#5',1.0),(6,'G#5',1.0),(7,'E5',0.8)]:
        place_mono(mel,whistle(nf(note),dur*BEAT,vibd=0.02),int(bar*BAR*SR))
    wL,wR=pingpong(mel,0.5,0.3,5)
    place(buf,mel,0,gain=0.18); buf[:,0]+=wL*0.10; buf[:,1]+=wR*0.10
    start=int((BARS-2)*BAR*SR); n=N-start; t=np.arange(n)/SR
    place(buf,hp(rng.standard_normal(n),500)*((t/(n/SR))**2)*0.5*0.16,start)
    for i,off in enumerate([0,0.25,0.5,0.75]):
        place(buf,tom(180-i*18),int((BARS-1)*BAR*SR)+b2s(3+off),gain=0.4)
    return np.tanh(buf*1.12)

# ============================================================================
def master(buf, target_rms=0.205):
    """RMS-targeted so western stages match the neon stages (~-13.5 dBFS), then soft-clip."""
    m=buf.copy(); m[:,0]=lp(m[:,0],14000); m[:,1]=lp(m[:,1],14000)
    r=np.sqrt(np.mean(m**2)) or 1.0
    m=m*(target_rms/r)
    m=np.tanh(m)                         # catch peaks, keep within unity
    p=np.max(np.abs(m)) or 1.0
    if p>0.97: m=m*(0.97/p)
    return m

def write_wav(path,st):
    out=(np.clip(st,-1,1)*32767).astype(np.int16)
    with wave.open(path,'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())

def main():
    outdir=sys.argv[1] if len(sys.argv)>1 else "."
    os.makedirs(outdir,exist_ok=True)
    print("rendering western layers...")
    layers=[L0_bed(),L1_tense(),L2_urgent(),L3_frantic()]
    for i,ly in enumerate(layers): write_wav(os.path.join(outdir,"stem%d.wav"%i),master(ly,0.16))
    acc=np.zeros((N,2)); rms=[]; demo=[]
    for i,ly in enumerate(layers):
        acc=acc+ly; st=master(acc)
        write_wav(os.path.join(outdir,"stage%d.wav"%(i+1)),st)
        rms.append(np.sqrt(np.mean(st**2))); demo.append(st)
    write_wav(os.path.join(outdir,"demo.wav"),np.concatenate(demo,axis=0))
    print("loop %.3fs bars=%d bpm=%g"%(N/SR,BARS,BPM))
    print("stage RMS: "+"  ".join("s%d=%.3f"%(i+1,r) for i,r in enumerate(rms)))

if __name__=="__main__":
    main()
