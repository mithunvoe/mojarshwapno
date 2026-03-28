"""Main entry point: load contacts from VCF, check all numbers in parallel, generate report."""

import os
import sys
import json
import csv
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from vcf_parser import parse_vcf
from scraper import check_phone, CheckResult


def find_vcf_file() -> Path:
    """Find the VCF file in the data directory."""
    data_dir = Path("data")
    vcf_files = list(data_dir.glob("*.vcf"))
    if not vcf_files:
        print("ERROR: No .vcf file found in ./data/ directory")
        print("Mount your VCF file: docker run -v /path/to/contacts.vcf:/app/data/contacts.vcf ...")
        sys.exit(1)
    if len(vcf_files) > 1:
        print(f"WARNING: Multiple VCF files found, using: {vcf_files[0].name}")
    return vcf_files[0]


def generate_reports(results: list[CheckResult], contact_names: dict[str, str], report_dir: Path) -> None:
    """Generate JSON, CSV, and text summary reports."""
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    found = [r for r in results if r.found]
    not_found = [r for r in results if not r.found and not r.error]
    errors = [r for r in results if r.error]

    # JSON report (full details)
    json_path = report_dir / f"report_{timestamp}.json"
    json_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_checked": len(results),
            "found_in_breach": len(found),
            "safe": len(not_found),
            "errors": len(errors),
        },
        "found": [
            {
                "phone": r.phone,
                "contact_name": contact_names.get(r.phone, ""),
                "name": r.name,
                "code": r.code,
                "mobile": r.mobile,
                "item_count": r.item_count,
                "purchases": [
                    {
                        "product": p.product,
                        "date": p.date,
                        "quantity": p.quantity,
                        "price": p.price,
                        "category": p.category,
                    }
                    for p in r.purchases
                ],
            }
            for r in found
        ],
        "safe": [{"phone": r.phone, "contact_name": contact_names.get(r.phone, "")} for r in not_found],
        "errors": [{"phone": r.phone, "contact_name": contact_names.get(r.phone, ""), "error": r.error} for r in errors],
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))

    # CSV report (summary per number)
    csv_path = report_dir / f"report_{timestamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Phone", "Contact Name", "Status", "Shwapno Name", "Items", "Error"])
        for r in results:
            status = "FOUND" if r.found else ("ERROR" if r.error else "SAFE")
            writer.writerow([r.phone, contact_names.get(r.phone, ""), status, r.name, r.item_count, r.error])

    # Text summary
    txt_path = report_dir / f"report_{timestamp}.txt"
    lines = [
        f"Shwapno Databreach Check Report",
        f"Generated: {datetime.now().isoformat()}",
        f"",
        f"SUMMARY",
        f"  Total checked:    {len(results)}",
        f"  Found in breach:  {len(found)}",
        f"  Safe:             {len(not_found)}",
        f"  Errors:           {len(errors)}",
        f"",
        f"{'='*60}",
        f"FOUND IN BREACH ({len(found)} numbers)",
        f"{'='*60}",
    ]
    for r in found:
        lines.append(f"")
        lines.append(f"  Contact: {contact_names.get(r.phone, 'Unknown')}")
        lines.append(f"  Phone:   {r.phone}")
        lines.append(f"  Name:    {r.name}")
        lines.append(f"  Items:   {r.item_count}")
        for p in r.purchases:
            lines.append(f"    - {p.product} | {p.date} | Qty {p.quantity} | {p.price} | {p.category}")

    if errors:
        lines.append(f"")
        lines.append(f"{'='*60}")
        lines.append(f"ERRORS ({len(errors)} numbers)")
        lines.append(f"{'='*60}")
        for r in errors:
            lines.append(f"  {contact_names.get(r.phone, 'Unknown')} ({r.phone}): {r.error}")

    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nReports saved to:")
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")
    print(f"  TXT:  {txt_path}")


def main() -> None:
    workers = int(os.environ.get("WORKERS", "10"))
    max_retries = int(os.environ.get("MAX_RETRIES", "5"))
    retry_delay = float(os.environ.get("RETRY_DELAY", "2"))

    vcf_path = find_vcf_file()
    contacts = parse_vcf(vcf_path)
    print(f"Loaded {len(contacts)} unique BD phone numbers from {vcf_path.name}")

    if not contacts:
        print("No valid Bangladeshi phone numbers found.")
        return

    contact_names: dict[str, str] = {c.phone: c.name for c in contacts}
    results: list[CheckResult] = []
    start_time = time.time()
    completed = 0
    found_count = 0

    print(f"Checking with {workers} parallel workers, {max_retries} retries per number...")
    print()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_contact = {
            pool.submit(check_phone, c.phone, max_retries, retry_delay): c
            for c in contacts
        }

        for future in as_completed(future_to_contact):
            contact = future_to_contact[future]
            try:
                result = future.result()
            except Exception as e:
                result = CheckResult(phone=contact.phone, found=False, error=str(e))

            results.append(result)
            completed += 1

            if result.found:
                found_count += 1
                status = f"FOUND  {result.name} ({result.item_count} items)"
            elif result.error:
                status = f"ERROR  {result.error[:50]}"
            else:
                status = "SAFE"

            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            eta = (len(contacts) - completed) / rate if rate > 0 else 0

            print(
                f"[{completed}/{len(contacts)}] "
                f"{contact.name:<25s} {contact.phone} -> {status} "
                f"({rate:.1f}/s, ETA {eta:.0f}s)"
            )

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Found: {found_count}/{len(contacts)}")

    generate_reports(results, contact_names, Path("reports"))


if __name__ == "__main__":
    main()
