import csv
import json
import glob

csv_files = glob.glob("uploads/**/batch1_*.csv", recursive=True)
print("Found CSVs:", csv_files)

for cf in csv_files:
    print(f"Reading {cf}:")
    with open(cf, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 2:
                break
            fname = row.get("File Name")
            data_str = row.get("Json Data")
            try:
                data = json.loads(data_str)
                inv = data.get("invoice", {})
                sub = data.get("subtotal", {})
                items = data.get("items", [])
                print(f"  {fname} -> Inv#: {inv.get('invoice_number')}, Seller: {inv.get('seller_name')}, Total: {sub.get('total')}, Items: {len(items)}")
            except Exception as e:
                print("Error parsing JSON for", fname, e)
