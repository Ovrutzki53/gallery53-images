import os, json, requests
KEY=os.environ["GEMINI_API_KEY"]; H={"x-goog-api-key":KEY}
B="https://generativelanguage.googleapis.com/v1beta"
ms,tok=[], ""
while True:
    j=requests.get(f"{B}/models?pageSize=1000&pageToken={tok}",headers=H,timeout=60).json()
    ms+=j.get("models",[]); tok=j.get("nextPageToken","")
    if not tok: break
for m in ms:
    n=m["name"]
    if any(k in n for k in ["omni","veo","video","lyria","antigravity"]) or "predictLongRunning" in m.get("supportedGenerationMethods",[]):
        m.pop("thinking",None)
        print("=== "+json.dumps(m,ensure_ascii=False).replace(KEY,"***"))
