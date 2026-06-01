#!/usr/bin/env python3
"""
Dead Giveaway - "Neon Concourse" background music.
Chill / hypnotic synthwave, one seamless loop.

Pure-numpy additive synthesis. Seamlessness is structural: every voice and the
ping-pong delay write into a fixed-length buffer with modulo-wrapped indices, so the
loop point has no click and the echoes carry across the seam.

Output: neon_loop.wav (16-bit stereo, 44.1 kHz). Encode to ogg/mp3 with ffmpeg after.
"""
import numpy as np, sys, wave, struct

SR   = 44100
BPM  = 84.0
BEAT = 60.0 / BPM
BAR  = BEAT * 4
BARS = 16
N    = int(round(BAR * BARS * SR))           # total loop samples
buf  = np.zeros((N, 2), dtype=np.float64)
rng  = np.random.default_rng(7)

def b2s(beats):                              # beats -> samples
    return int(round(beats * BEAT * SR))

# ---- note frequencies ------------------------------------------------------
A4 = 440.0
def nf(name):
    names = {'C':-9,'C#':-8,'D':-7,'D#':-6,'E':-5,'F':-4,'F#':-3,
             'G':-2,'G#':-1,'A':0,'A#':1,'B':2}
    p = name[:-1]; octv = int(name[-1])
    semis = names[p] + (octv - 4) * 12
    return A4 * 2 ** (semis / 12.0)

# ---- envelopes & filters ---------------------------------------------------
def adsr(n, a, d, s, r):
    a, d, r = max(1, int(a*SR)), max(1, int(d*SR)), max(1, int(r*SR))
    s_len = max(0, n - a - d - r)
    if a + d + r > n:                        # squeeze for very short notes
        a = max(1, int(n*0.1)); d = max(1, int(n*0.2)); r = max(1, int(n*0.3))
        s_len = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, s, d, endpoint=False),
        np.full(s_len, s),
        np.linspace(s, 0, r),
    ])
    if len(env) < n: env = np.pad(env, (0, n-len(env)), constant_values=0)
    return env[:n]

def lowpass(x, cutoff):                       # one-pole, gentle/warm
    a = np.exp(-2*np.pi*cutoff/SR)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1-a)*x[i] + a*acc; y[i] = acc
    return y

def lp_fast(x, cutoff):
    """One-pole lowpass as a truncated exponential-kernel convolution (vectorized).
    y[i] = b * sum_k a^k x[i-k]; kernel truncated where a^k < 1e-4 (short for high cutoffs)."""
    a = np.exp(-2*np.pi*cutoff/SR); b = 1-a
    if a <= 0: return x.copy()
    K = int(np.ceil(np.log(1e-4)/np.log(a)))
    K = max(4, min(K, 8000))
    h = b * (a ** np.arange(K))
    return np.convolve(x, h)[:len(x)]

# ---- oscillators -----------------------------------------------------------
def osc(freq, n, wave='saw', detune=0.0):
    t = np.arange(n)/SR
    f = freq * (2 ** (detune/1200.0))
    ph = f*t
    if wave=='sine': return np.sin(2*np.pi*ph)
    if wave=='tri':  return 2*np.abs(2*(ph-np.floor(ph+0.5)))-1
    if wave=='square': return np.sign(np.sin(2*np.pi*ph))
    # saw
    return 2*(ph-np.floor(ph+0.5))

# ---- placement (wrapped, equal-power pan) ----------------------------------
def place(sig, pos, pan=0.0, gain=1.0):
    n = len(sig)
    idx = (pos + np.arange(n)) % N
    gl = np.cos((pan+1)*np.pi/4) * gain
    gr = np.sin((pan+1)*np.pi/4) * gain
    np.add.at(buf[:,0], idx, sig*gl)
    np.add.at(buf[:,1], idx, sig*gr)

# ---------------------------------------------------------------------------
# CHORDS  (i - VI - III - VII in A minor):  Am  F  C  G   x4
# ---------------------------------------------------------------------------
PROG = [
    ('Am', ['A3','C4','E4'], 'A2'),
    ('F',  ['A3','C4','F4'], 'F2'),
    ('C',  ['G3','C4','E4'], 'C2'),
    ('G',  ['G3','B3','D4'], 'G2'),
] * 4

# ---- PAD: stacked detuned saws per chord tone, slow attack, warm lowpass ---
for bar,(name,tones,root) in enumerate(PROG):
    pos = bar*int(BAR*SR)
    n   = int(BAR*SR)
    env = adsr(n, a=0.5, d=0.4, s=0.85, r=0.6)
    for ti,tone in enumerate(tones):
        f = nf(tone)
        voice = ( osc(f, n,'saw',-7) + osc(f, n,'saw',+7) + 0.6*osc(f, n,'saw',0) )/2.6
        voice = lp_fast(voice, 1400) * env
        pan = -0.4 + 0.4*ti                  # spread tones across stereo
        place(voice, pos, pan=pan, gain=0.16)

# ---- SUB BASS: smooth root, pulses on beats 1 & 3 (half-time) --------------
for bar,(name,tones,root) in enumerate(PROG):
    base = bar*int(BAR*SR)
    f = nf(root)
    for beat in (0, 2):
        n = b2s(1.8)
        env = adsr(n, 0.01, 0.15, 0.7, 0.5)
        sig = (osc(f, n,'sine') + 0.35*osc(f, n,'tri'))*env
        place(sig, base+b2s(beat), pan=0.0, gain=0.5)

# ---- ARP: gentle 8th-note triangle pluck, hypnotic ping-pong delay ---------
arp_dry = np.zeros(N)
arp_pan = []  # collect (pos,len) to pan later via delay; we render dry mono then delay
for bar,(name,tones,root) in enumerate(PROG):
    base = bar*int(BAR*SR)
    pattern = [tones[0], tones[1], tones[2], tones[1]] * 2   # up-ish, 8 eighths/bar
    for i,tone in enumerate(pattern):
        f = nf(tone)*2                       # one octave up, sparkly
        n = b2s(0.5)
        env = adsr(n, 0.005, 0.12, 0.0, 0.05)  # plucky
        sig = (osc(f, n,'tri') + 0.25*osc(f, n,'sine'))*env
        pos = base + b2s(i*0.5)
        idx = (pos+np.arange(n)) % N
        np.add.at(arp_dry, idx, sig)

# ping-pong delay (dotted 8th), wrapped -> seamless
def pingpong(mono, delay_beats=0.75, fb=0.4, taps=6):
    L = np.zeros(N); R = np.zeros(N)
    d = b2s(delay_beats)
    cur = mono.copy(); amp = 1.0; left = True
    L += mono*0.0; R += mono*0.0
    for k in range(taps):
        amp *= fb
        shift = ((k+1)*d) % N
        rolled = np.roll(cur, shift) * amp
        if left: L += rolled
        else:    R += rolled
        left = not left
    return L, R

dL, dR = pingpong(arp_dry, 0.75, 0.45, 7)
# dry arp centered + wet pingpong sides
place(arp_dry, 0, pan=0.0, gain=0.10)
buf[:,0] += dL*0.12
buf[:,1] += dR*0.12

# ---- LEAD: sparse, soft, only on bars 4,8,12,16 (the G turnaround) ---------
LEAD = {  # (bar, beat): note
    3:[('E5',0,1.5),('D5',1.5,1.0),('C5',2.5,1.5)],
    7:[('G5',0,2.0),('E5',2.0,2.0)],
    11:[('A5',0,1.5),('G5',1.5,1.0),('E5',2.5,1.5)],
    15:[('D5',0,2.0),('C5',2.0,1.0),('B4',3.0,1.0)],
}
lead_dry = np.zeros(N)
for bar, notes in LEAD.items():
    base = bar*int(BAR*SR)
    for tone, beat, dur in notes:
        f = nf(tone)
        n = b2s(dur)
        env = adsr(n, 0.04, 0.2, 0.6, 0.4)
        sig = (osc(f, n,'sine') + 0.3*osc(f, n,'tri') + 0.12*osc(f,n,'saw',+5))*env
        sig = lp_fast(sig, 2600)
        idx = (base+b2s(beat)+np.arange(n)) % N
        np.add.at(lead_dry, idx, sig)
lL, lR = pingpong(lead_dry, 0.75, 0.35, 6)
place(lead_dry, 0, pan=0.0, gain=0.16)
buf[:,0] += lL*0.10; buf[:,1] += lR*0.10

# ---- DRUMS: chill half-time groove -----------------------------------------
def kick(nbeats=0.5):
    n=b2s(nbeats); t=np.arange(n)/SR
    f=50+70*np.exp(-t*30)
    ph=2*np.pi*np.cumsum(f)/SR
    env=np.exp(-t*8)
    return np.sin(ph)*env

def snare(nbeats=0.5):
    n=b2s(nbeats); t=np.arange(n)/SR
    noise=rng.standard_normal(n)*np.exp(-t*22)
    tone=np.sin(2*np.pi*190*t)*np.exp(-t*30)*0.5
    return lp_fast(noise,6000)*0.8+tone

def hat(nbeats=0.18, open_=False):
    n=b2s(nbeats); t=np.arange(n)/SR
    noise=rng.standard_normal(n)*np.exp(-t*(40 if not open_ else 14))
    return noise - lp_fast(noise, 7000)      # crude highpass

for bar in range(BARS):
    base=bar*int(BAR*SR)
    place(kick(),  base+b2s(0),   gain=0.9)          # downbeat
    place(kick(0.4), base+b2s(2.5), gain=0.5)        # soft pickup
    place(snare(), base+b2s(2),   gain=0.5)          # backbeat (half-time)
    for e in range(8):                               # soft swung eighths
        sw = 0.06 if e%2 else 0.0
        place(hat(open_=(e==7)), base+b2s(e*0.5+sw), pan=0.15*(-1)**e, gain=0.16)

# ---------------------------------------------------------------------------
# master: gentle bus lowpass shimmer removal, soft limiter, normalize
# ---------------------------------------------------------------------------
mix = buf.copy()
# light high cut for warmth
mix[:,0] = lp_fast(mix[:,0], 12000)
mix[:,1] = lp_fast(mix[:,1], 12000)
# soft saturation/limiter
mix = np.tanh(mix*1.1)
peak = np.max(np.abs(mix))
mix = mix / peak * 0.89                              # ~ -1 dBFS headroom

# write WAV (16-bit PCM stereo)
out = (mix*32767).astype(np.int16)
path = sys.argv[1] if len(sys.argv)>1 else "neon_loop.wav"
with wave.open(path,'w') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(out.tobytes())

dur = N/SR
print(f"wrote {path}  dur={dur:.2f}s  bars={BARS}  bpm={BPM}  peak={peak:.3f}")
print(f"seam check: head[0]={out[0].tolist()} tail[-1]={out[-1].tolist()}")
