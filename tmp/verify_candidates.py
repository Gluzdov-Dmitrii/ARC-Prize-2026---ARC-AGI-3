from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
from kagglesdk.search.types.search_api_service import ListEntitiesRequest, ListEntitiesFilters
from kagglesdk.search.types.search_enums import DocumentType, PrivacyFilter

api = KaggleApi()
api.authenticate()

refs = [
    "jakobbrggen/duck-qwen3-8-anim-base",
    "keithtyser/duck-qwen3-8-flash-next-nvfp4-mtp",
    "dantelok/duck-qwen3-8-flash-next-nvfp4-mtp",
    "kashyapsinhgohil/duck-qwen3-8-flash-next-nvfp4-mtp",
    "mosorio1/flashnext-sub",
    "rakbidb/sukirman-verified-exact-profile-flash-next-mtp3",
    "analyticaobscura/i-guess-it-s-just-luck-thanks-foysal",
    "ahmedmohamedfergany/barbados-2",
    "anhadmahajan06/arc-agi-3-fluid-intelligence-agent",
    "vladimiryakunin/arc-prize-2026-lcld-qwen-v10",
    "yocybercode/thui-v3-1",
    "yocybercode/thui-v3-2",
    "yocybercode/thui-v5-2",
    "thtennant/arc3-duck-v22",
    "kunaldesale2408/duck-harness-fast-eval",
    "lucifer19/blackcat-dual-mind-router-c05",
    "xiaoyan12/lb-9-arc3-duck-v16-with-gpt-oss-120b",
    "justforgags/arc3-duck-lora-sft",
    "kai57sh/arc-agi3-vlm-test",
    "sonnvo/strong2-best6-hardgate-finetune-24e",
]

print("=== GET KERNEL ===")
with api.build_kaggle_client() as kg:
    for ref in refs:
        owner, slug = ref.split("/", 1)
        req = ApiGetKernelRequest()
        req.user_name = owner
        req.kernel_slug = slug
        try:
            k = kg.kernels.kernels_api_client.get_kernel(req)
        except Exception as e:
            print(f"FAIL {ref}: {type(e).__name__} {e}")
            continue
        m = k.metadata
        comps = []
        for attr in ("competition_sources", "competitions", "competition_data_sources"):
            if hasattr(m, attr):
                val = getattr(m, attr)
                if val:
                    comps.append((attr, val))
        print("---", ref)
        print("  title", m.title)
        print("  ver", m.current_version_number, "internet", m.enable_internet, "gpu", m.enable_gpu, "private", m.is_private)
        print("  machine", getattr(m, "machine_shape", None))
        print("  last_run", getattr(m, "last_run_time", None) or getattr(m, "evaluation_date", None))
        # dump score-like and source-like
        for name in dir(m):
            low = name.lower()
            if any(x in low for x in ("score", "compet", "dataset", "model_source", "internet", "gpu", "machine", "status")):
                try:
                    val = getattr(m, name)
                except Exception:
                    continue
                if callable(val) or name.startswith("_"):
                    continue
                if val in (None, "", [], {}):
                    continue
                s = str(val)
                if len(s) > 220:
                    s = s[:220] + "..."
                print(f"  meta.{name} = {s}")

    print("\n=== PRECISE SEARCH ===")
    for q in [
        "jakobbrggen duck-qwen3-8-anim-base",
        "keithtyser duck-qwen3-8-flash-next-nvfp4-mtp",
        "dantelok duck-qwen3-8-flash-next-nvfp4-mtp",
        "ahmedmohamedfergany barbados-2",
        "anhadmahajan06 fluid intelligence",
        "vladimiryakunin lcld",
    ]:
        req = ListEntitiesRequest()
        f = ListEntitiesFilters()
        f.query = q
        f.document_types = [DocumentType.KERNEL]
        f.privacy = PrivacyFilter.PUBLIC
        req.filters = f
        req.page_size = 5
        resp = kg.search.search_api_client.list_entities(req)
        docs = []
        for attr in dir(resp):
            if attr.startswith("_"):
                continue
            val = getattr(resp, attr)
            if isinstance(val, list) and val:
                docs = val
                break
        print("Q", q)
        for d in docs[:5]:
            title = getattr(d, "title", "")
            kd = getattr(d, "kernel_document", None)
            score = getattr(kd, "best_public_score", None) if kd else None
            slug = getattr(d, "slug", None) or getattr(d, "ref", None)
            owner = None
            # owner nested
            for a in ("owner_user_name", "author_user_name", "user_name"):
                if hasattr(d, a) and getattr(d, a):
                    owner = getattr(d, a)
                    break
            print(f"  score={score} owner={owner} slug={slug} title={title}")
            # print extra identifiers
            for a in ("id", "document_id", "canonical_url"):
                if hasattr(d, a) and getattr(d, a):
                    print(f"    {a}={getattr(d,a)}")