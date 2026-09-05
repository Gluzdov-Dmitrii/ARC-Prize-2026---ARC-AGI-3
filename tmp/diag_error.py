from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.competitions.types.competition_api_service import ApiGetSubmissionRequest
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

api = KaggleApi(); api.authenticate()
with api.build_kaggle_client() as kg:
    print("=== SUBMISSIONS ===")
    for ref in (56008249, 56005599, 55974010, 55959595):
        r = ApiGetSubmissionRequest(); r.ref = ref
        s = kg.competitions.competition_api_client.get_submission(r)
        print("---", ref, "---")
        for n in ("status","error_description","public_score","private_score","total_bytes","file_name","description","date","url"):
            print(f"  {n}={getattr(s,n)!r}")
    print("\n=== KERNEL OURS ===")
    r = ApiGetKernelRequest(); r.user_name="dmitriigluzdov"; r.kernel_slug="arc-prize-2026-lcld-qwen-v10"
    resp = kg.kernels.kernels_api_client.get_kernel(r)
    m = resp.metadata
    for n in dir(m):
        if n.startswith("_"): continue
        try:
            v = getattr(m, n)
        except Exception:
            continue
        if callable(v): continue
        sv = str(v)
        if len(sv) > 500: sv = sv[:500]+"..."
        print(f"  {n}={sv}")
    print("\n=== KERNEL AUTHOR ===")
    r = ApiGetKernelRequest(); r.user_name="vladimiryakunin"; r.kernel_slug="arc-prize-2026-lcld-qwen-v10"
    resp = kg.kernels.kernels_api_client.get_kernel(r)
    m = resp.metadata
    for n in ("current_version_number","enable_internet","machine_shape","is_private","title","language","kernel_type","enable_gpu","enable_tpu"):
        print(f"  {n}={getattr(m,n,None)!r}")
    # datasets
    for attr in dir(m):
        if "dataset" in attr.lower() or "competit" in attr.lower() or "model" in attr.lower() or "source" in attr.lower():
            try:
                v = getattr(m, attr)
            except Exception:
                continue
            if callable(v): continue
            print(f"  {attr}={v!r}"[:800])