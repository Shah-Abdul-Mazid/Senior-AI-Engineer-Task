import urllib.request
import json

res = urllib.request.urlopen("http://localhost:8000/api/v1/documents/").read()
docs = json.loads(res)
for d in docs:
    doc_id = d["document_id"]
    res2 = urllib.request.urlopen(f"http://localhost:8000/api/v1/documents/{doc_id}/result").read()
    data = json.loads(res2)
    inv = data.get("invoice") or {}
    sname = inv.get("supplier_name")
    sname_str = (sname[:30] + "...") if sname else "None"
    print(d["filename"], "-> Inv#:", inv.get("invoice_number"), "| Supplier:", sname_str, "| Total:", inv.get("total"))
