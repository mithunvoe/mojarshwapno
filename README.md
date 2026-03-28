# Shwapno Databreach Checker

Bulk-check your contacts against the Shwapno grocery chain databreach. Feed it a VCF (vCard) file and it checks every Bangladeshi phone number in parallel, generating a report of who was affected and what purchase data was leaked.

## How it works

1. **Parse VCF** - Extracts all phone numbers from your contacts file, normalizes them to `01XXXXXXXXX` format (strips `+880`, `880` prefixes), deduplicates
2. **Scrape** - For each number, hits `https://shwapnocheck.2bd.net/` with a fresh session + CSRF token. The server is flaky, so each number is retried up to 5 times on failure
3. **Parallel execution** - Uses a thread pool (default 10 workers) to check multiple numbers simultaneously
4. **Report** - Generates three report formats:
   - **JSON** - Full structured data (customer info + every purchase item)
   - **CSV** - One row per number (phone, status, name, item count)
   - **TXT** - Human-readable summary with purchase details

## Project structure

```
.
├── checker.py        # Main entrypoint - orchestrates VCF loading, parallel checking, report generation
├── vcf_parser.py     # VCF parser + BD phone number normalizer
├── scraper.py        # HTTP scraper with CSRF handling, retries, HTML parsing
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── data/             # Place your .vcf file here
│   └── contacts.vcf
└── reports/          # Generated reports appear here
    ├── report_YYYYMMDD_HHMMSS.json
    ├── report_YYYYMMDD_HHMMSS.csv
    └── report_YYYYMMDD_HHMMSS.txt
```

## Setup

### 1. Add your contacts

Create a `data/` directory and place your VCF file inside it. The file **must** have a `.vcf` extension. Any name works - the checker picks up the first `.vcf` it finds:

```bash
mkdir -p data
cp /path/to/your/contacts.vcf data/
```

If you export from Android/Google Contacts/Telegram, the default export name is fine (e.g. `Contacts_20260328.vcf`).

### 2. Configure (optional)

Copy the example and edit values:

```bash
cp .env.example .env
```

### 3. Run

#### With Docker (recommended)

```bash
docker compose run --rm checker
```

#### Without Docker

```bash
pip install -r requirements.txt
python checker.py
```

## Configuration

All settings are via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKERS` | `10` | Number of parallel threads |
| `MAX_RETRIES` | `5` | Retry attempts per number (server returns 403 randomly) |
| `RETRY_DELAY` | `2` | Seconds to wait between retries |

Example with custom settings:

```bash
# Docker
WORKERS=15 MAX_RETRIES=8 docker compose run --rm checker

# Direct
WORKERS=20 MAX_RETRIES=10 RETRY_DELAY=1 python checker.py
```

## Output

Live progress while running:

```
[42/325] Rana                      01714386942 -> FOUND  Rana (15 items) (3.1/s, ETA 91s)
[43/325] Karim                     01812345678 -> SAFE (3.0/s, ETA 94s)
```

Final summary:

```
Done in 118.6s
  Found: 20/325
```

## Notes

- The checker website is flaky. Some numbers may fail with 403 errors even after retries. Re-running usually picks them up
- Only Bangladeshi mobile numbers (11 digits, starting with `01`) are checked. Foreign numbers and landlines are skipped
- Each request creates a fresh HTTP session with a new CSRF token to handle the server's stateless CSRF validation
