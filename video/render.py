"""Render the demo film: every frame of video/index.html (window.renderAt(t)) captured in headless Edge and piped into
ffmpeg, then muxed with the voiceover (out/voice.wav) and the music bed (out/music.wav from music.py).
Adapted from the build-a-dataset film pipeline.
  python video/render.py --stills 3 10 20     # PNG stills -> out/still-*.png (also writes out/beats.json)
  python video/render.py                      # full film -> out/dashboard-royale-demo.mp4"""
import json, pathlib, subprocess, sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
OUT = HERE / "out"
FPS = 30


def main():
    args = sys.argv[1:]
    cues = json.loads((OUT / "cues.json").read_text(encoding="utf-8"))
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        pg.on("pageerror", lambda e: print("PAGE ERROR:", e))
        pg.goto((HERE / "index.html").resolve().as_uri())
        info = pg.evaluate("([c, s]) => FILM.init(c, s)", [cues, script])
        total = info["total"]
        # preload every screenshot so frames never catch a half-decoded image
        pg.evaluate("""() => Promise.all([...new Set(FILM_SHOTS())].map(s => new Promise(r => { const i = new Image(); i.onload = i.onerror = r; i.src = 'assets/' + s + '.png'; document.body.appendChild(Object.assign(i, {style: 'position:absolute;left:-9999px;width:10px'})); })))""".replace("FILM_SHOTS()", json.dumps([l["shot"] for l in script["lines"]])))
        (OUT / "beats.json").write_text(json.dumps(pg.evaluate("FILM.beats"), indent=1), encoding="utf-8")
        if args and args[0] == "--stills":
            for s in args[1:]:
                pg.evaluate(f"renderAt({float(s)})"); pg.wait_for_timeout(60)
                pg.screenshot(path=OUT / f"still-{float(s):06.1f}.png")
            print("stills done"); return
        n = int(round(total * FPS))
        silent = OUT / "picture.mp4"
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", str(silent)],
                              stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate(f"renderAt({i / FPS})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
            if i % 300 == 0:
                print(f"frame {i}/{n}", flush=True)
        ff.stdin.close(); ff.wait()
        b.close()
    final = OUT / "dashboard-royale-demo.mp4"
    music = OUT / "music.wav"
    inputs = ["-i", str(silent), "-i", str(OUT / "voice.wav")]
    if music.exists():
        inputs += ["-i", str(music)]
        mix = "[1:a]volume=1.0[v];[2:a]volume=0.8[m];[v][m]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    else:
        mix = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", mix, "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", str(final)], check=True)
    print("wrote", final, f"{total:.1f} s")


main()
