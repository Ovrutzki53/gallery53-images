"""Image-to-video with Gemini Omni via the Interactions API (google-genai).
Run one explicitly named job: python scripts/omni.py <job-name>
omni_jobs/<name>.json: {"type":"image_to_video","name":..,"model":"gemini-omni-1.1-flash","aspect_ratio":"9:16",
  "resolution":"720p","duration":"6s","sources":["path or url"],"prompt":".."}
Output: out/reels/<name>/clip.mp4 + done.json. One clip per job, no automatic retry once the request is accepted.
"""
import base64, datetime, json, os, pathlib, sys, time, requests
from google import genai
KEY = os.environ["GEMINI_API_KEY"]
def scrub(s): return str(s).replace(KEY, "***")
def img_b64(src):
    b = requests.get(src, timeout=60).content if src.startswith("http") else pathlib.Path(src).read_bytes()
    mime = "image/png" if src.lower().split("?")[0].endswith(".png") else "image/jpeg"
    return base64.b64encode(b).decode(), mime
def dump(o):
    try: return o.model_dump(mode="json", exclude_none=True)
    except Exception: return str(o)
def main(name):
    job = json.loads(pathlib.Path(f"omni_jobs/{name}.json").read_text())
    out = pathlib.Path("out/reels") / name
    if (out / "done.json").exists(): print("already done", name); return
    out.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=KEY, http_options={"api_version": "v1beta"})
    inp = [{"type": "text", "text": job["prompt"]}]
    for s in job["sources"]:
        d, m = img_b64(s); inp.append({"type": "image", "data": d, "mime_type": m})
    kw = {}
    if job.get("type"): kw["generation_config"] = {"video_config": {"task": job["type"]}}
    it = client.interactions.create(
        model=job.get("model", "gemini-omni-1.1-flash"), input=inp, background=True,
        response_format={"type": "video", "aspect_ratio": job.get("aspect_ratio", "9:16"),
                         "duration": job.get("duration", "6s"), "resolution": job.get("resolution", "720p")}, **kw)
    iid = it.id; print("interaction", iid, it.status)
    for _ in range(180):
        if it.status not in ("in_progress", "queued", "idle"): break
        time.sleep(10); it = client.interactions.get(iid)
    print("final status", it.status)
    meta = dump(it)
    vid = getattr(it, "output_video", None)
    if it.status != "completed" or vid is None:
        # look for a video inside steps
        for st in (meta.get("steps") or []) if isinstance(meta, dict) else []:
            for c in json.dumps(st) and [st]: pass
        (out / "error.json").write_text(scrub(json.dumps({k: v for k, v in meta.items() if k not in ("input",)}, indent=1, default=str)[:20000]) if isinstance(meta, dict) else scrub(meta))
        raise SystemExit(f"no video: status={it.status}")
    if getattr(vid, "data", None):
        data = vid.data if isinstance(vid.data, (bytes, bytearray)) else base64.b64decode(vid.data)
    else:
        r = requests.get(vid.uri, headers={"x-goog-api-key": KEY}, timeout=300); r.raise_for_status(); data = r.content
    (out / "clip.mp4").write_bytes(data)
    usage = meta.get("usage") if isinstance(meta, dict) else None
    (out / "done.json").write_text(json.dumps({"job": name, "model": job.get("model"), "status": it.status, "usage": usage,
                                               "at": datetime.datetime.utcnow().isoformat()}, indent=1, default=str))
    p = pathlib.Path("usage") / f"omni-{datetime.date.today():%Y-%m}.json"; p.parent.mkdir(exist_ok=True)
    u = json.loads(p.read_text()) if p.exists() else {"clips": 0, "seconds": 0}
    u["clips"] += 1; u["seconds"] += int(str(job.get("duration", "6s")).rstrip("s")); p.write_text(json.dumps(u, indent=1))
    print("saved", out / "clip.mp4", len(data))
if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("usage: omni.py <job-name>")
    try: main(sys.argv[1])
    except SystemExit: raise
    except Exception as e: raise SystemExit("ERROR " + scrub(e))
