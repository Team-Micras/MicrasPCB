# Query JLCPCB's public parts search (same endpoint as tools/micras_pcb/jlc.py) by keyword/MPN.
import json, sys, urllib.request
def q(kw):
    req = urllib.request.Request(
        "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
        data=json.dumps({"keyword": kw, "currentPage": 1, "pageSize": 10}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "micras-pcb"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    out = []
    for c in (d.get("data") or {}).get("componentPageInfo", {}).get("list") or []:
        pr = c.get("componentPrices") or [{}]
        out.append((c.get("componentCode"), c.get("componentModelEn"), c.get("componentSpecificationEn"),
                    c.get("componentLibraryType"), c.get("stockCount"),
                    [(p.get("startNumber"), p.get("productPrice")) for p in pr[:4]]))
    return out
for kw in sys.argv[1:]:
    print("==", kw)
    try:
        for row in q(kw): print("  ", row)
    except Exception as e:
        print("  ERR", e)
