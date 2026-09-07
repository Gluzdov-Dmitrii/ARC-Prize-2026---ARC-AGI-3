import json
import urllib.request
print("pypi", urllib.request.urlopen("https://pypi.org", timeout=20).status)
print("bootstrap", urllib.request.urlopen("https://bootstrap.pypa.io/get-pip.py", timeout=20).status)
print("hf", urllib.request.urlopen("https://huggingface.co/api/models/Qwen/Qwen3.8-27B-FP8", timeout=30).status)
raw = urllib.request.urlopen("https://huggingface.co/api/models/Qwen/Qwen3.8-27B-FP8", timeout=30).read()
data = json.loads(raw)
safes = [s for s in data.get("safetensors", {}).get("parameters", {})]
print("pipeline", data.get("pipeline_tag"), "library", data.get("library_name"), "usedStorage", data.get("usedStorage"))
print("safetensors_keys", list((data.get("safetensors") or {}).keys())[:8])
