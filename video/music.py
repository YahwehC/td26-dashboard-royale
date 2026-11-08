"""Soft music bed for the demo film, synthesised here (no samples): warm pad chords + a light plucked arpeggio
at 96 BPM, ducked under the voiceover using the cue sheet, plus whooshes/pops synced to the morphs (out/beats.json). Writes out/music.wav (48 kHz stereo).
Run after voice.py: python video/music.py"""
import json, pathlib, wave

import numpy as np

HERE = pathlib.Path(__file__).parent
OUT = HERE / "out"
SR = 48000
cues = json.loads((OUT / "cues.json").read_text(encoding="utf-8"))
total = cues["total"]
n = int(total * SR)
t = np.arange(n) / SR
BPM = 96
beat = 60 / BPM
bar = beat * 4


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# I - vi - IV - V in C major, voiced warm and low
CHORDS = [[48, 55, 64, 67, 71], [45, 52, 60, 64, 67], [41, 48, 57, 60, 64], [43, 50, 59, 62, 67]]
pad = np.zeros(n)
pluck = np.zeros(n)
rng = np.random.default_rng(7)
for b in range(int(total / bar) + 1):
    ch = CHORDS[b % 4]
    s0, s1 = int(b * bar * SR), min(n, int((b + 1) * bar * SR + 0.6 * SR))
    if s0 >= n:
        break
    tt = t[s0:s1] - b * bar
    env = np.minimum(1, tt / 0.8) * np.exp(-np.maximum(0, tt - bar) * 3)
    for m in ch:
        f = midi(m)
        pad[s0:s1] += env * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt + 0.3)) / len(ch)
    # arpeggio: 8th notes over the chord, an octave up
    for k in range(8):
        m = ch[[1, 2, 3, 4, 3, 2, 3, 4][k]] + 12
        a0 = int((b * bar + k * beat / 2) * SR)
        a1 = min(n, a0 + int(0.9 * SR))
        if a0 >= n:
            break
        ta = t[a0:a1] - t[a0]
        f = midi(m)
        tone = np.sin(2 * np.pi * f * ta) + 0.35 * np.sin(2 * np.pi * 2 * f * ta) + 0.12 * np.sin(2 * np.pi * 3 * f * ta)
        pluck[a0:a1] += tone * np.exp(-ta * 6.5) * (0.75 + 0.25 * rng.random())

mix = 0.55 * pad + 0.22 * pluck

# ---- sound effects synced to the film (out/beats.json, written by render.py): a pitched whoosh per morph that peaks
# at the circle moment, a plucky pop when the new icon lands, soft ticks for cursor clicks, screen swaps and chips.
sfx = np.zeros(n)
PENTA = [60, 62, 64, 67, 69, 72, 74, 76, 79]
beats_f = OUT / "beats.json"
if beats_f.exists():
    beats = json.loads(beats_f.read_text(encoding="utf-8"))
    rs = np.random.default_rng(3)

    def put(sig, at):
        a0 = int(at * SR)
        if a0 < 0:
            sig, a0 = sig[-a0:], 0
        a1 = min(n, a0 + len(sig))
        if a1 > a0:
            sfx[a0:a1] += sig[:a1 - a0]

    def resonant(noise, fc, q=6.0):
        # 2-pole band-pass with a time-varying centre frequency (one sample at a time; short signals only)
        y = np.zeros_like(noise); y1 = y2 = 0.0
        for i in range(len(noise)):
            w = 2 * np.pi * fc[i] / SR; r = 1 - w / (2 * q); c = 2 * r * np.cos(w)
            y0 = (1 - r) * noise[i] + c * y1 - r * r * y2
            y[i] = y0; y2, y1 = y1, y0
        return y

    def whoosh(dur, f0, big):
        m = int((dur + 0.15) * SR); x = np.linspace(0, 1, m)
        env = np.sin(np.pi * x) ** 1.6
        fc = f0 * (1 + 3.2 * np.sin(np.pi * x) ** 2)
        w = resonant(rs.standard_normal(m), fc) * env
        w /= np.max(np.abs(w)) + 1e-9
        tt = np.arange(m) / SR
        tone_ = 0.25 * np.sin(2 * np.pi * np.cumsum(fc * 0.5) / SR) * env
        return (w + tone_) * (1.0 if big else 0.55)

    def pop(f, amp=1.0):
        m = int(0.32 * SR); tt = np.arange(m) / SR
        fr = f * (1 + 0.9 * np.exp(-tt / 0.012))
        s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-tt / 0.07)
        s += 0.4 * np.sin(2 * np.pi * 2 * np.cumsum(fr) / SR) * np.exp(-tt / 0.04)
        s += 0.8 * np.sin(2 * np.pi * 62 * tt) * np.exp(-tt / 0.11)          # soft low thump
        return amp * s

    def tick(f=2400, amp=0.5, d=0.025):
        m = int(0.06 * SR); tt = np.arange(m) / SR
        return amp * (np.sin(2 * np.pi * f * tt) * np.exp(-tt / d) + 0.3 * rs.standard_normal(m) * np.exp(-tt / 0.004))

    for i, mo in enumerate(beats["morphs"]):
        f0 = midi(PENTA[i % len(PENTA)])
        put(0.5 * whoosh(mo["dur"], f0 * 2, mo["big"]), mo["t"] - 0.12)
    for i, lt in enumerate(beats["lands"]):
        put(0.55 * pop(midi(PENTA[i % len(PENTA)] + 12)), lt - 0.02)
    for ct in beats["clicks"]:
        put(tick(3200, 0.7, 0.012), ct)
    for st in beats["swaps"]:
        put(0.3 * whoosh(0.35, 1400, False), st - 0.05)
    for pt in beats["pops"]:
        put(tick(1500, 0.25, 0.03), pt)
    sfx = sfx / (np.max(np.abs(sfx)) + 1e-9)
# fade in/out
mix *= np.minimum(1, t / 1.5) * np.minimum(1, (total - t) / 2.5)
# duck under the voice (smooth gain: 1.0 in gaps, 0.45 while someone speaks)
gate = np.zeros(n)
for c in cues["cues"]:
    gate[int(c["start"] * SR):int(c["end"] * SR)] = 1
k = int(0.25 * SR)
cs = np.concatenate([[0], np.cumsum(gate)])          # moving average via cumulative sum (fast)
lo = np.clip(np.arange(n) - k // 2, 0, n); hi = np.clip(np.arange(n) + k // 2, 0, n)
gate = (cs[hi] - cs[lo]) / k
mix *= 1 - 0.55 * gate
mix = mix / np.max(np.abs(mix)) * 10 ** (-20 / 20)   # peak -20 dBFS: a bed under the voice
mix += sfx * (1 - 0.35 * gate) * 10 ** (-17 / 20)    # effects sit a little above the bed
# light stereo width
left = mix + 0.08 * np.roll(pluck, 480) * 10 ** (-20 / 20)
right = mix - 0.08 * np.roll(pluck, 480) * 10 ** (-20 / 20)
st = np.stack([left, right], 1)
st = np.clip(st, -1, 1)
with wave.open(str(OUT / "music.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype("<i2").tobytes())
print("music.wav", f"{total:.1f} s")
