"""
generate_data.py  -  Recreates the synthetic purchase order dataset.

Creates 120 fictional vendors, then writes 2,500 purchase orders where the
vendor name is often misspelled, abbreviated, or decorated with suffixes and
tags, the way names drift in a real purchasing system. It also writes an
answer key with the true vendor for every purchase order, so cleaning
methods can be scored exactly.

All company names are invented. Seed 4 reproduces the files in this repo.

Run:  python generate_data.py
"""

import csv
import datetime
import random

SEED = 4
N_VENDORS = 120
N_ORDERS = 2500

random.seed(SEED)

PREFIXES = ["Pacific", "Summit", "Redwood", "Coastal", "Granite", "Sierra",
            "Harbor", "Golden State", "Monterey", "Cascade", "Ironwood",
            "Blue Ridge", "Northstar", "Keystone", "Silverline", "Bayview",
            "Vanguard", "Evergreen", "Pinnacle", "Delta", "Frontier",
            "Liberty", "Cypress", "Atlas", "Meridian"]

# (business type, spend category)
CORES = [("Freight", "Logistics"), ("Logistics", "Logistics"),
         ("Packaging", "Packaging"), ("Steel", "Raw Materials"),
         ("Plastics", "Raw Materials"), ("Electronics", "Components"),
         ("Semiconductor", "Components"), ("Fasteners", "Components"),
         ("Industrial Supply", "MRO"), ("Tooling", "MRO"),
         ("Chemical", "Raw Materials"),
         ("Manufacturing", "Contract Manufacturing"),
         ("Technologies", "Components"), ("Office Products", "Office"),
         ("Staffing Services", "Services"),
         ("Environmental Services", "Services"), ("Trucking", "Logistics"),
         ("Warehousing", "Logistics")]

SUFFIXES = ["Inc", "LLC", "Corporation", "Company", "Ltd", ""]

# Ways each legal suffix gets written in practice
SUFFIX_VARIANTS = {
    "Inc": ["Inc", "Inc.", "INC", "Incorporated", ", Inc.", ""],
    "LLC": ["LLC", "L.L.C.", "Llc", ", LLC", ""],
    "Corporation": ["Corporation", "Corp", "Corp.", "CORP", ""],
    "Company": ["Company", "Co", "Co.", ""],
    "Ltd": ["Ltd", "Ltd.", "Limited", ""],
}

# Common abbreviations and near-spellings
ABBREVIATIONS = {
    "Manufacturing": ["Mfg", "Mfg.", "Manuf"],
    "Technologies": ["Tech", "Technology", "Techs"],
    "Services": ["Svcs", "Svc", "Services"],
    "Industrial": ["Indl", "Ind."],
    "Electronics": ["Elec", "Electronic"],
    "Semiconductor": ["Semi", "Semiconductors"],
    "Logistics": ["Logistic", "Logistics"],
    "Products": ["Prods", "Prod"],
    "Environmental": ["Env", "Enviro"],
    "Golden State": ["Golden St", "GoldenState"],
    "Warehousing": ["Whse", "Warehouse"],
    "Packaging": ["Pkg", "Packaging"],
}


def make_vendors():
    """Create unique fictional vendors: {vendor_id: (full name, category)}."""
    vendors = {}
    used = set()
    while len(vendors) < N_VENDORS:
        prefix = random.choice(PREFIXES)
        core, category = random.choice(CORES)
        suffix = random.choice(SUFFIXES)
        base = f"{prefix} {core}"
        if base in used:
            continue
        used.add(base)
        if random.random() < 0.15:
            base = "The " + base
        full = (base + " " + suffix).strip()
        vendors[f"V{len(vendors) + 1:03d}"] = (full, category)
    return vendors


def typo(text):
    """Drop, swap, or double one letter."""
    i = random.randrange(1, len(text) - 1)
    if text[i] == " ":
        return text
    r = random.random()
    if r < 0.4:
        return text[:i] + text[i + 1:]                         # drop
    if r < 0.7:
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]  # swap
    return text[:i] + text[i] + text[i:]                        # double


def dirty(full):
    """Return a messy version of a vendor's true name."""
    parts = full.split()
    suffix = parts[-1] if parts[-1] in SUFFIX_VARIANTS else None
    body = " ".join(parts[:-1]) if suffix else full

    if random.random() < 0.5 and body.startswith("The "):
        body = body[4:]
    for word, options in ABBREVIATIONS.items():
        if word in body and random.random() < 0.3:
            body = body.replace(word, random.choice(options))
    if random.random() < 0.12:
        body = typo(body)

    if suffix:
        s = random.choice(SUFFIX_VARIANTS[suffix])
    else:
        s = random.choice(["", "", "", "", " Inc"])
    out = body + ((s if s.startswith(",") else " " + s) if s else "")

    r = random.random()
    if r < 0.2:
        out = out.upper()
    elif r < 0.3:
        out = out.lower()
    if random.random() < 0.08:
        out = out + random.choice([" - CA", " (Remit)", " #2", " - AP"])
    if random.random() < 0.1:
        out = "  " + out + " "
    if random.random() < 0.05:
        out = out.replace(" ", "  ", 1)
    return out


def main():
    vendors = make_vendors()
    ids = list(vendors)
    # Uneven spend across vendors, and each vendor gets its own
    # chance of being typed correctly.
    weights = [random.lognormvariate(0, 0.7) for _ in ids]
    clean_rate = {v: random.choice([0.05, 0.1, 0.2, 0.4, 0.7]) for v in ids}

    rows, key = [], []
    start = datetime.date(2025, 1, 1)
    for n in range(1, N_ORDERS + 1):
        vid = random.choices(ids, weights)[0]
        full, category = vendors[vid]
        raw = full if random.random() < clean_rate[vid] else dirty(full)
        order_date = start + datetime.timedelta(days=random.randrange(0, 650))
        amount = round(random.lognormvariate(8, 1.1), 2)
        po = f"PO-{100000 + n}"
        rows.append([po, order_date.isoformat(), raw, category, amount])
        key.append([po, vid, full])

    with open("purchase_orders_messy_v2.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["po_id", "order_date", "vendor_name_raw", "category",
                    "amount_usd"])
        w.writerows(rows)
    with open("answer_key_v2.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["po_id", "true_vendor_id", "true_vendor_name"])
        w.writerows(key)
    print(f"Wrote {N_ORDERS:,} purchase orders for {len(set(k[1] for k in key))} vendors.")


if __name__ == "__main__":
    main()
