"""Split importance of the stage 1 gate-candidate trees (mean of 3 seeds) -> results/b92/stage1_importance.json (needs build/b92 pickles)."""
import json
import pickle

import numpy as np

from .stage1 import BUILD, RES

NAMES = ["bid_sz", "ask_sz", "spread", "imb_bucket", "trade_sign_sum", "ofi16", "last_mid_dir"]


def main():
    out = {}
    for g in ("b87", "hawkes"):
        imp = np.mean([pickle.load(open(BUILD / f"{g}_lagfeat16_gbt_s{s}.pkl", "rb")).feature_importances_ for s in range(3)], axis=0)
        h = imp[7:]
        top = np.argsort(h)[::-1][:5]
        out[g] = {"current_columns_total": round(float(imp[:7].sum()), 3), "lagged_columns_total": round(float(h.sum()), 3),
                  "top_lagged": [{"feature": NAMES[i % 7], "lag": int(i // 7 + 1), "importance": round(float(h[i]), 4)} for i in top],
                  "by_lag": [round(float(x), 4) for x in h.reshape(16, 7).sum(1)]}
    (RES / "stage1_importance.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out)[:300])


if __name__ == "__main__":
    main()
