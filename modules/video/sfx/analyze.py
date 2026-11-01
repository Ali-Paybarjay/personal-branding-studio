import array, math, subprocess, sys, json, re, glob, os
def analyze(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "48000", "-f", "s16le", "-"], capture_output=True).stdout
    a = array.array("h"); a.frombytes(raw[: len(raw) // 2 * 2])
    n = 480  # 10 ms
    rms = []
    for i in range(0, len(a), n):
        ch = a[i:i+n]
        ms = math.sumprod(ch, ch) / len(ch) if len(ch) else 0
        rms.append(10 * math.log10(ms / 32768.0**2 + 1e-12))
    # بلندی اوج: میانگین ۵۰ میلی‌ثانیه‌ی دور هر قاب (وسط‌چین، نه رو به جلو)
    sm = []
    for i in range(len(rms)):
        win = rms[max(0, i - 2): i + 3]
        sm.append(10 * math.log10(sum(10 ** (x / 10) for x in win) / len(win) + 1e-12))
    peak_db = max(sm)
    praw = max(rms)
    onset = next(i for i, x in enumerate(rms) if x > praw - 24)
    hit = next(i for i, x in enumerate(rms) if x > praw - 4)     # لحظه‌ی ضربه: اولین قاب نزدیک اوج
    pk = max(range(len(rms)), key=lambda i: rms[i])
    end = max(i for i, x in enumerate(rms) if x > praw - 40)
    spk = max(abs(x) for x in a) / 32768.0 if a else 0
    return {"dur": round(len(a) / 48000, 3), "onset": round(onset * 0.01, 3), "hit": round(hit * 0.01, 3), "peakAt": round(pk * 0.01, 3),
            "end": round((end + 1) * 0.01, 3), "peakRms": round(peak_db, 1), "samplePk": round(20 * math.log10(spk + 1e-9), 1)}
if __name__ == "__main__":
    for p in sys.argv[1:]:
        r = analyze(p)
        print(f"{os.path.basename(p):28s} dur {r['dur']:6.2f} onset {r['onset']:5.2f} hit {r['hit']:5.2f} peakAt {r['peakAt']:5.2f} end {r['end']:5.2f} peakRms {r['peakRms']:6.1f} spk {r['samplePk']:6.1f}")
