"""Download full-size originals listed in backup/*.json into originals/<handle>/NN.ext before they are removed from Shopify."""
import json, pathlib, requests
ROOT = pathlib.Path(__file__).resolve().parent.parent
for f in (ROOT/"backup").glob("*.json"):
    for handle, urls in json.loads(f.read_text()).items():
        d = ROOT/"originals"/handle; d.mkdir(parents=True, exist_ok=True)
        for n, u in enumerate(urls):
            ext = u.split("?")[0].rsplit(".", 1)[-1][:4]
            p = d/f"{n:02d}.{ext}"
            if p.exists(): continue
            r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok: p.write_bytes(r.content)
            else: print("FAIL", handle, n, r.status_code)
