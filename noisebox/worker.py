"""Calculation worker process (started by engine.py; not for direct use).

    python -s worker.py <workdir> <k>

Reads job.pkl and chunks_<k>.pkl, computes its blocks with the Python core, writes prog_<k>.txt while it works and
res_<k>.pkl at the end.
"""
import os
import pickle
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(work, k):
    from noisebox import engine
    with open(os.path.join(work, "job.pkl"), "rb") as f:
        spec = pickle.load(f)
    with open(os.path.join(work, "chunks_%s.pkl" % k), "rb") as f:
        mine = pickle.load(f)
    job, kind = spec["job"], spec["kind"]
    engine.core()
    out = []
    for n, (i, chunk) in enumerate(mine):
        out.append((i, engine.field_chunk(job, chunk) if kind == "field" else engine.points_chunk(job, chunk)))
        with open(os.path.join(work, "prog_%s.txt" % k), "w") as f:
            f.write(str(n + 1))
    with open(os.path.join(work, "res_%s.pkl" % k), "wb") as f:
        pickle.dump(out, f, protocol=4)


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2])
    except Exception:                                                # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
