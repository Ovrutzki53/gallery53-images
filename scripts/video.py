"""Image-to-video with Veo (Gemini API).
video_jobs/<name>.json: {"image": "video/x.jpg" or URL, "prompt": "...", "model": "veo-3.1-lite-generate-preview",
                         "duration": 8, "aspect": "9:16", "resolution": "1080p", "negative": "..."}
Output: out_video/<name>/clip.mp4 + done.json. Skips jobs that already have done.json.
"""
import base64, datetime, json, os, pathlib, sys, time, requests
KEY = os.environ.get("GEMINI_API_KEY", "")
BASE = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": KEY, "Content-Type": "application/json"}
def scrub(s): return str(s).replace(KEY, "***") if KEY else str(s)
def load_image(src):
    if src.startswith("http"):
        r = requests.get(src, timeout=60); r.raise_for_status(); b = r.content
    else:
        b = pathlib.Path(src).read_bytes()
    mime = "image/png" if src.lower().split("?")[0].endswith(".png") else "image/jpeg"
    return base64.b64encode(b).decode(), mime
def usage_add(model, seconds):
    p = pathlib.Path("usage") / f"video-{datetime.date.today():%Y-%m}.json"; p.parent.mkdir(exist_ok=True)
    d = json.loads(p.read_text()) if p.exists() else {"clips": 0, "seconds": 0, "by_model": {}}
    d["clips"] += 1; d["seconds"] += seconds; d["by_model"][model] = d["by_model"].get(model, 0) + seconds
    p.write_text(json.dumps(d, indent=2))
def run(job_path):
    name = job_path.stem; out = pathlib.Path("out_video") / name
    if (out / "done.json").exists(): print("skip", name); return
    out.mkdir(parents=True, exist_ok=True)
    job = json.loads(job_path.read_text()); model = job.get("model", "veo-3.1-lite-generate-preview")
    b64, mime = load_image(job["image"])
    params = {"aspectRatio": job.get("aspect", "9:16"), "durationSeconds": int(job.get("duration", 8))}
    if job.get("resolution"): params["resolution"] = job["resolution"]
    if job.get("negative"): params["negativePrompt"] = job["negative"]
    body = {"instances": [{"prompt": job["prompt"], "image": {"bytesBase64Encoded": b64, "mimeType": mime}}], "parameters": params}
    r = requests.post(f"{BASE}/models/{model}:predictLongRunning", headers=H, json=body, timeout=120)
    if r.status_code == 404:
        ms = requests.get(f"{BASE}/models?pageSize=200", headers=H, timeout=60).json().get("models", [])
        print("ALL MODELS:", [m["name"] + " " + ",".join(m.get("supportedGenerationMethods", [])) for m in ms])
    if r.status_code != 200: raise RuntimeError(f"start HTTP {r.status_code}: {scrub(r.text[:600])}")
    op = r.json()["name"]; print("operation", op)
    for _ in range(120):
        time.sleep(10)
        s = requests.get(f"{BASE}/{op}", headers=H, timeout=60).json()
        if s.get("done"): break
    else: raise RuntimeError("timeout waiting for video")
    if "error" in s: raise RuntimeError(scrub(json.dumps(s["error"])[:600]))
    usage_add(model, params["durationSeconds"])
    samples = s["response"]["generateVideoResponse"]["generatedSamples"]
    for i, smp in enumerate(samples):
        v = requests.get(smp["video"]["uri"], headers={"x-goog-api-key": KEY}, timeout=300, allow_redirects=True)
        v.raise_for_status(); (out / f"clip{'' if i == 0 else '-' + str(i)}.mp4").write_bytes(v.content)
    (out / "done.json").write_text(json.dumps({"job": name, "model": model, "params": params, "clips": len(samples)}, indent=2))
    print("done", name, len(samples))
if __name__ == "__main__":
    names = sys.argv[1:]
    jobs = [pathlib.Path("video_jobs") / f"{n}.json" for n in names] if names else sorted(pathlib.Path("video_jobs").glob("*.json"))
    errs = []
    for j in jobs:
        try: run(j)
        except Exception as e: print("ERROR", j.name, scrub(e)); errs.append(j.name)
    if errs: sys.exit(1)
