from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.search.types.search_api_service import ListEntitiesRequest, ListEntitiesFilters
from kagglesdk.search.types.search_enums import DocumentType, PrivacyFilter
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

api = KaggleApi()
api.authenticate()

queries = [
    "Duck Qwen3.8 Flash Next NVFP4 MTP",
    "Duck Qwen3.8 Anim Base",
    "I guess it's just luck Thanks Foysal",
    "sukirman Flash-Next MTP3",
    "flashnext-sub",
    "Thui v3.1",
    "Thui v5",
    "Thui v6",
    "arc3 duck v22",
    "duck-harness-fast-eval",
    "LCLD Qwen",
    "GPT-OSS 120B",
    "Sangita Bannore",
    "dantelok flash next",
    "blackcat dual-mind",
    "justforgags lora",
    "xiaoyan12 gpt-oss",
    "flames56 gpt-oss",
    "vladimiryakunin lcld",
    "yocybercode thui",
    "arc-prize-2026-arc-agi-3",
]

rows = []
with api.build_kaggle_client() as kg:
    seen = set()
    for q in queries:
        req = ListEntitiesRequest()
        f = ListEntitiesFilters()
        f.query = q
        f.document_types = [DocumentType.KERNEL]
        f.privacy = PrivacyFilter.PUBLIC
        req.filters = f
        req.page_size = 25
        try:
            resp = kg.search.search_api_client.list_entities(req)
        except Exception as e:
            print("SEARCH FAIL", q, type(e).__name__, e)
            continue
        docs = getattr(resp, "documents", None) or getattr(resp, "entities", None) or []
        if not docs and hasattr(resp, "items"):
            docs = resp.items
        # try common attr names
        if not docs:
            for attr in dir(resp):
                if attr.startswith("_"):
                    continue
                val = getattr(resp, attr)
                if isinstance(val, list) and val:
                    docs = val
                    break
        for d in docs or []:
            title = getattr(d, "title", None) or getattr(d, "name", None) or ""
            slug = ""
            owner = ""
            # nested
            for attr in ("ref", "slug", "kernel_slug"):
                if hasattr(d, attr) and getattr(d, attr):
                    slug = str(getattr(d, attr))
                    break
            kd = getattr(d, "kernel_document", None)
            score = None
            if kd is not None:
                score = getattr(kd, "best_public_score", None)
            if score is None:
                score = getattr(d, "best_public_score", None)
            author = getattr(d, "author_name", None) or getattr(d, "owner_user_name", None) or ""
            url = getattr(d, "canonical_url", None) or getattr(d, "url", None) or ""
            key = (title, slug, url)
            if key in seen:
                continue
            seen.add(key)
            rows.append((float(score or 0), title, author, slug, url, q))

print("=== SEARCH HITS ===")
for r in sorted(rows, key=lambda x: -x[0])[:60]:
    print(f"{r[0]:7.3f} | {r[1][:55]:55s} | {str(r[2])[:20]:20s} | {r[3][:40]} | q={r[4][:40] if False else r[5][:30]}")

print("\n=== GETKERNEL SCORES via search docs dump sample ===")
print("n_rows", len(rows))