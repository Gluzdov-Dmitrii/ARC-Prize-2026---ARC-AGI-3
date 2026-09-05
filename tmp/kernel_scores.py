from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

api = KaggleApi(); api.authenticate()
refs = [
    ("dmitriigluzdov","duck-qwen3-8-flash-next-nvfp4-mtp"),
    ("samrishb","just-seeing-what-can-i-change-to-make-it-better"),
    ("jakobbrggen","duck-qwen3-8-anim-base"),
    ("dantelok","duck-qwen3-8-flash-next-nvfp4-mtp"),
    ("keithtyser","duck-qwen3-8-flash-next-nvfp4-mtp"),
    ("anhadmahajan06","arc-agi-3-fluid-intelligence-agent"),
    ("thtennant","arc3-duck-v22"),
    ("kunaldesale2408","duck-harness-fast-eval"),
    ("analyticaobscura","i-guess-it-s-just-luck-thanks-foysal"),
]
with api.build_kaggle_client() as kg:
    for user, slug in refs:
        r = ApiGetKernelRequest(); r.user_name=user; r.kernel_slug=slug
        try:
            resp = kg.kernels.kernels_api_client.get_kernel(r)
        except Exception as e:
            print(f"FAIL {user}/{slug}: {e}")
            continue
        m = resp.metadata
        # score fields on metadata
        score_attrs = []
        for n in dir(m):
            if "score" in n.lower() or "vote" in n.lower() or n in ("current_version_number","enable_internet","machine_shape","is_private","last_run_time","title"):
                try:
                    v = getattr(m,n)
                except Exception:
                    continue
                if callable(v): continue
                score_attrs.append(f"{n}={v!r}")
        print(f"=== {user}/{slug} ===")
        print(" ", " | ".join(score_attrs)[:500])
        print("  datasets", getattr(m,"dataset_data_sources",None))
        print("  models", getattr(m,"model_data_sources",None))
        print("  docker", str(getattr(m,"docker_image",""))[-20:])