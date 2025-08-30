# api/oscals_loader.py
import json, os
from sqlalchemy import text as sql

def load_controls_and_baselines(session):
    # Idempotent insert of controls from catalog JSON
    catalog_path = os.path.join(os.path.dirname(__file__), "oscals", "800-53_rev5_2_0_catalog.json")
    with open(catalog_path, "r", encoding="utf-8") as f:
        cat = json.load(f)
    controls = []
    def walk(ctrl, family=None):
        cid = ctrl["id"]
        fam = cid.split("-")[0]
        txt = " ".join([ctrl.get("title",""), *(p.get("prose","") for p in ctrl.get("parts",[]) if p.get("name")=="statement")]).strip()
        params = [p["id"] for p in ctrl.get("params",[])]
        controls.append((cid, fam or fam, txt, json.dumps(params)))
        for sub in ctrl.get("controls", []): walk(sub, fam)
    for c in cat["catalog"]["controls"]:
        walk(c)

    session.execute(sql("""
        INSERT INTO controls (id, family, text, parameters)
        VALUES (:id, :family, :text, :params)
        ON CONFLICT (id) DO NOTHING
    """), [{"id": i, "family": f, "text": t, "params": p} for (i,f,t,p) in controls])

    # Load 800-53B baseline profiles (Low/Moderate/High)
    def load_profile(fn):
        with open(os.path.join(os.path.dirname(__file__), "oscals", fn), "r", encoding="utf-8") as f:
            prof = json.load(f)
        # Resolve included controls from profile imports
        cids = []
        for imp in prof["profile"].get("imports", []):
            for sel in imp.get("include-controls", []):
                for c in sel.get("with-ids", []):
                    cids.append(c)
        return sorted(set(cids))

    low  = load_profile("800-53B_low_baseline_profile.json")
    mod  = load_profile("800-53B_moderate_baseline_profile.json")
    high = load_profile("800-53B_high_baseline_profile.json")

    for bid, cids in [("LOW", low), ("MODERATE", mod), ("HIGH", high)]:
        session.execute(sql("""
            INSERT INTO baselines (id, control_ids)
            VALUES (:id, :cids)
            ON CONFLICT (id) DO UPDATE SET control_ids = EXCLUDED.control_ids
        """), {"id": bid, "cids": cids})

    session.commit()
