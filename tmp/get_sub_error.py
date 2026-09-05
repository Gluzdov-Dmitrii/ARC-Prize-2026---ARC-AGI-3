from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.competitions.types.competition_api_service import ApiGetSubmissionRequest

api = KaggleApi(); api.authenticate()
with api.build_kaggle_client() as kg:
    r = ApiGetSubmissionRequest(); r.ref = 56005599
    s = kg.competitions.competition_api_client.get_submission(r)
    for n in dir(s):
        if n.startswith('_'): continue
        try:
            v = getattr(s, n)
        except Exception:
            continue
        if callable(v): continue
        print(f"{n}={v!r}")