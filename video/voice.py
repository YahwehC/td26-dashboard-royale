"""Voiceover for the demo video: one TTS clip per script line (Microsoft Edge neural voice via edge-tts),
then a cue sheet (video/out/cues.json) with each line's start/end, which the picture (video/index.html) reads.
Run: .venv/Scripts/python.exe video/voice.py"""
import asyncio, json, subprocess, pathlib

import edge_tts

HERE = pathlib.Path(__file__).parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
S = json.loads((HERE / "script.json").read_text(encoding="utf-8"))


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


async def main():
    t = S["lead_in"]
    cues = []
    for ln in S["lines"]:
        mp3 = OUT / f"vo-{ln['id']}.mp3"
        for attempt in range(8):   # the free endpoint drops requests now and then
            if mp3.exists() and mp3.stat().st_size > 0:
                break
            try:
                await edge_tts.Communicate(ln["text"], S["voice"], rate=S["rate"]).save(str(mp3))
            except Exception as e:  # noqa: BLE001
                print("retry", ln["id"], type(e).__name__)
                mp3.unlink(missing_ok=True)
                await asyncio.sleep(2 + attempt * 2)
        d = duration(mp3)
        cues.append({"id": ln["id"], "text": ln["text"], "start": round(t, 3), "end": round(t + d, 3), "file": mp3.name})
        t += d + S["gap"] + ln.get("pause", 0)
    total = round(t - S["gap"] + S["tail"], 3)
    (OUT / "cues.json").write_text(json.dumps({"total": total, "cues": cues}, indent=1), encoding="utf-8")
    # voice track: each clip placed at its start time
    args = ["ffmpeg", "-y", "-v", "error"]
    for c in cues:
        args += ["-i", str(OUT / c["file"])]
    parts = [f"[{i}:a]aresample=48000,adelay={int(c['start'] * 1000)}:all=1[a{i}]" for i, c in enumerate(cues)]
    mix = "".join(f"[a{i}]" for i in range(len(cues))) + f"amix=inputs={len(cues)}:normalize=0,apad=whole_dur={total}[v]"
    args += ["-filter_complex", ";".join(parts) + ";" + mix, "-map", "[v]", "-ac", "2", "-ar", "48000", str(OUT / "voice.wav")]
    subprocess.run(args, check=True)
    print(f"{len(cues)} lines, total {total:.1f} s")


asyncio.run(main())
