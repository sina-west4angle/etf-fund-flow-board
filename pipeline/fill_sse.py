import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ThreadPoolExecutor
from build_data import _sse_one, load_json, save_json
lo, hi = sys.argv[1], sys.argv[2]
idx = load_json("index_daily.json")
days = [d for d in sorted(idx.keys()) if lo <= d <= hi]
todo = [d for d in days if load_json(f"sse_{d.replace('-','')}.json") is None]
print(f"fill {lo}..{hi}: {len(todo)} to do", flush=True)
done = [0]
def work(d):
    try:
        m = _sse_one(d)
        if len(m) > 100:
            save_json(f"sse_{d.replace('-','')}.json", m)
    except Exception as e:
        print("FAIL", d, str(e)[:80], flush=True)
    done[0] += 1
    if done[0] % 20 == 0: print(f"  fill {done[0]}/{len(todo)}", flush=True)
with ThreadPoolExecutor(max_workers=3) as ex:
    list(ex.map(work, todo))
print("fill done", flush=True)
