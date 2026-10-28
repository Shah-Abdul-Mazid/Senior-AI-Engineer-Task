import urllib.request
import json
import time

for name in ['0000223278.tif', 'batch1-0494.jpg', 'invoice.xlsx']:
    req = urllib.request.Request(f'http://localhost:8000/api/v1/documents/load-sample?filename={name}', method='POST')
    res = urllib.request.urlopen(req).read()
    data = json.loads(res)
    print('Enqueued sample:', name, '-> Document ID:', data['document_id'])

# Allow pipeline a few moments to finish
time.sleep(4)

res = urllib.request.urlopen('http://localhost:8000/api/v1/documents/').read()
docs = json.loads(res)
print(f"\n--- Current Documents in Queue ({len(docs)}) ---")
for d in docs:
    doc_id = d['document_id']
    res2 = urllib.request.urlopen(f'http://localhost:8000/api/v1/documents/{doc_id}/result').read()
    res_data = json.loads(res2)
    inv = res_data.get('invoice') or {}
    sname = (inv.get('supplier_name') or 'N/A')[:25]
    cname = (inv.get('customer_name') or 'N/A')[:25]
    print(f"File: {d['filename']:<16} [{d['file_type']:<4}] -> Status: {d['status']:<15} | Inv#: {str(inv.get('invoice_number')):<15} | Total: ${str(inv.get('total')):<10} | Vendor: {sname:<25} | Cust: {cname:<25} | Items: {len(inv.get('line_items') or [])}")
