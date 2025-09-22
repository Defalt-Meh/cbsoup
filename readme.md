# cbsoup

Benchmarks an optimized `Session` against `requests + BeautifulSoup`, fetching HTML and downloading CSS/JS assets. Results are saved under `./res`.

## 1) Set up & run

```bash
# (optional) use a fresh venv
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# install deps
pip install -U pip
pip install -r requirements.txt

# run the benchmark (defaults to https://www.amazon.com/)
python bench_scrape.py

# examples:
python bench_scrape.py --iters 5 --warmup 1 --timeout 20
python bench_scrape.py --url https://www.amazon.com/ --url https://www.python.org/ --iters 3
python bench_scrape.py --csv res/summary.csv
