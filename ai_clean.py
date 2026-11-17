"""
ai_clean.py  -  Step 3: clean vendor names with an LLM, then score it.

What it does:
  1. Reads your workbook (the Clean_3 column you built in Excel).
  2. Sends the distinct Clean_3 names to Claude and asks it to group
     spellings that are the same company.
  3. Scores the rules-only result and the rules+AI result against the
     answer key, using the same yardstick for both.
  4. Saves the AI's mapping to ai_mapping.csv and the scored rows to
     scored_rows.csv so you can load them into Excel / Power BI.

Run it from the project folder:
    python ai_clean.py                              (main run)
    python ai_clean.py --no-hints                   (no abbreviation hints)
    python ai_clean.py --model claude-haiku-5-5     (smaller, cheaper model)
The extra runs save to their own files, so the main results are kept.
"""

import argparse
import json
import time

import anthropic
import pandas as pd

WORKBOOK = "purchase_orders_messy_v2.xlsx"
DATA_SHEET = "purchase_orders_messy_v2"
KEY_SHEET = "answer_key_v2"
MODEL = "claude-sonnet-5-5"

# Abbreviation hints given to the model. The --no-hints run leaves these out
# to test how well the model does without being told what to look for.
HINTS = """ (MFG = MANUFACTURING, PKG = PACKAGING,
IND or INDL = INDUSTRIAL, SVC or SVCS = SERVICES, TECH or TECHS = TECHNOLOGIES,
SEMI = SEMICONDUCTOR, ELEC = ELECTRONICS, WHSE = WAREHOUSING, ENV or ENVIRO =
ENVIRONMENTAL, PROD or PRODS = PRODUCTS, GOLDEN ST = GOLDEN STATE)"""

PROMPT = """You are cleaning vendor names from a purchase order system.

Below is a numbered list of vendor names. Many are different spellings of
the same company: typos, abbreviations{hints}, missing
or extra letters, and missing spaces.

Rules:
- Group names only when they are clearly the same company.
- Names that share a first word but have a different business are DIFFERENT
  companies. Example: LIBERTY TOOLING and LIBERTY PLASTICS are not the same.
- For each group, choose one standard name: the full, correctly spelled
  version in capital letters, with no abbreviations.

Return ONLY a JSON object that maps every number to its standard name,
like {{"1": "ACME FREIGHT", "2": "ACME FREIGHT", "3": "BOLT SUPPLY"}}.
Include every number. No explanation, no code fences.

Vendor names:
{names}
"""


def load_data():
    """Read the purchase orders and attach the true vendor for each row."""
    df = pd.read_excel(WORKBOOK, sheet_name=DATA_SHEET)
    df = df[["po_id", "vendor_name_raw", "amount_usd", "Clean_3"]]
    if df["Clean_3"].isna().any():
        raise SystemExit(
            "Clean_3 has empty cells. Open the workbook in Excel, press "
            "Ctrl+S to save, close it, and run this again."
        )
    try:
        key = pd.read_excel(WORKBOOK, sheet_name=KEY_SHEET)
    except ValueError:
        key = pd.read_csv("answer_key_v2.csv")
    return df.merge(key[["po_id", "true_vendor_id"]], on="po_id")


def ask_claude(names, model, use_hints):
    """Send the distinct names to Claude; get back {name: standard name}."""
    numbered = "\n".join(f"{i}. {n}" for i, n in enumerate(names, start=1))
    prompt = PROMPT.format(names=numbered, hints=HINTS if use_hints else "")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    start = time.time()
    # Streaming keeps the connection open for a long reply.
    with client.messages.stream(
        model=model,
        max_tokens=32000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    seconds = time.time() - start
    if message.stop_reason == "max_tokens":
        raise SystemExit("The reply was cut off. Raise max_tokens and rerun.")

    # The reply can contain "thinking" blocks before the answer.
    # Keep only the text blocks.
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    text = text[text.find("{"): text.rfind("}") + 1]  # ignore stray text
    answer = json.loads(text)

    mapping = {}
    missing = 0
    for i, name in enumerate(names, start=1):
        standard = answer.get(str(i))
        if not standard:          # the model skipped this one: keep as is
            standard = name
            missing += 1
        mapping[name] = str(standard).strip().upper()

    usage = message.usage
    print(f"Model: {model}   Hints: {'yes' if use_hints else 'no'}")
    print(f"Time: {seconds:.0f} seconds")
    print(f"Tokens: {usage.input_tokens:,} in, {usage.output_tokens:,} out")
    if missing:
        print(f"Note: the model skipped {missing} names (left unchanged).")
    return mapping


def accuracy(df, group_col):
    """
    Share of purchase orders placed in the right vendor group.

    Each true vendor gets ONE group: the group holding most of its rows,
    as long as that vendor is also the most common vendor in that group.
    Rows in that group count as correct. Rows stranded in other groups
    (split) or mixed into another vendor's group (wrong merge) are wrong.
    """
    counts = df.groupby([group_col, "true_vendor_id"]).size().reset_index(name="n")
    top_vendor_of_group = counts.loc[counts.groupby(group_col)["n"].idxmax()]
    top_group_of_vendor = counts.loc[counts.groupby("true_vendor_id")["n"].idxmax()]
    good = top_vendor_of_group.merge(
        top_group_of_vendor, on=[group_col, "true_vendor_id", "n"]
    )
    good_pairs = set(zip(good[group_col], good["true_vendor_id"]))
    correct = [
        (g, v) in good_pairs for g, v in zip(df[group_col], df["true_vendor_id"])
    ]
    return sum(correct) / len(df), correct


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--no-hints", action="store_true")
    args = parser.parse_args()
    # Extra runs get a suffix so they don't overwrite the main results.
    suffix = ""
    if args.model != MODEL:
        suffix += "_" + args.model
    if args.no_hints:
        suffix += "_nohints"

    df = load_data()
    names = sorted(df["Clean_3"].unique())
    print(f"Rows: {len(df):,}   Distinct Clean_3 names sent to AI: {len(names)}")
    print()

    mapping = ask_claude(names, args.model, not args.no_hints)
    df["ai_vendor"] = df["Clean_3"].map(mapping)

    rules_acc, df["rules_correct"] = accuracy(df, "Clean_3")
    ai_acc, df["ai_correct"] = accuracy(df, "ai_vendor")
    true_count = df["true_vendor_id"].nunique()

    print()
    print(f"{'Method':<14}{'Distinct vendors':>18}{'Accuracy':>11}")
    print(f"{'Raw names':<14}{df['vendor_name_raw'].nunique():>18,}{'':>11}")
    print(f"{'Rules only':<14}{df['Clean_3'].nunique():>18,}{rules_acc:>11.1%}")
    print(f"{'Rules + AI':<14}{df['ai_vendor'].nunique():>18,}{ai_acc:>11.1%}")
    print(f"{'True answer':<14}{true_count:>18,}{'100.0%':>11}")

    top = df.groupby("ai_vendor")["amount_usd"].sum().nlargest(5)
    print("\nTop 5 vendors by spend after AI cleaning:")
    for vendor, amount in top.items():
        print(f"  {vendor:<34}${amount:>14,.2f}")

    pd.DataFrame(
        sorted(mapping.items()), columns=["Clean_3", "ai_vendor"]
    ).to_csv(f"ai_mapping{suffix}.csv", index=False)
    df.to_csv(f"scored_rows{suffix}.csv", index=False)
    print(f"\nSaved ai_mapping{suffix}.csv and scored_rows{suffix}.csv")

    wrong = df[~pd.Series(df["ai_correct"])]
    if len(wrong):
        print(f"\nRows the AI got wrong: {len(wrong)}. Examples:")
        print(wrong[["vendor_name_raw", "ai_vendor"]].drop_duplicates().head(10).to_string(index=False))


if __name__ == "__main__":
    main()
