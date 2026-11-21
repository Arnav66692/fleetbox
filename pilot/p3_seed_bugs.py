import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p3_build_tasks import DESKTOP, TREES, check_tree, extract, git  # noqa: E402

REPO = DESKTOP / "Research-and-Papers/workspace-dynamics"
TARGET = "src/wsdyn/evaluation.py"
TEST = "tests/test_evaluation.py"
MUTANTS = [
    ("auroc-midrank", "midrank = (start + 1 + end) / 2", "midrank = (start + end) / 2",
     "auroc() in wsdyn gives wrong AUROC values, for example a perfect ranking no longer scores 1.0."),
    ("cf7-gate", "elif numerator <= 15 * denominator:", "elif numerator < 15 * denominator:",
     "validate_cf7_label() rejects rows whose effect is exactly 15 percent as dead-zone rows, but 15 percent should count as False."),
    ("accuracy-threshold", "(p >= 0.5) == y", "(p > 0.5) == y",
     "metrics() reports the wrong accuracy when a predicted probability is exactly 0.5."),
    ("duplicate-claims", "if not isinstance(key, str) or not key or key in indexed:", "if not isinstance(key, str) or not key:",
     "index_rows() silently accepts duplicate claim_id values instead of raising ValueError."),
    ("blind-metadata", 'result["messages"] = [\n        {"role": msg["role"], "content": msg["content"]} for msg in result["messages"]\n    ]',
     'result["messages"] = list(result["messages"])',
     "blind_claim() lets extra metadata nested inside messages through to the blinded output."),
    ("bootstrap-floor", "if type(bootstrap) is not int or bootstrap < 100:", "if type(bootstrap) is not int or bootstrap < 1:",
     "paired_analysis() accepts fewer than 100 bootstrap draws instead of raising ValueError."),
]

if __name__ == "__main__":
    head = git(REPO, "rev-parse", "--short", "HEAD").decode().strip()
    clean = TREES / f"wsdyn-{head}-clean"
    if not clean.exists():
        extract(REPO, "HEAD", clean)
    check = f"python -m pytest -q -x -p no:cacheprovider {TEST}"
    code, out = check_tree(clean, check)
    print(json.dumps({"clean_exit": code}))
    rows = []
    for name, old, new, symptom in MUTANTS:
        tree = TREES / f"wsdyn-{name}" / "base"
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(clean, tree)
        src = (tree / TARGET).read_text()
        assert src.count(old) == 1, name
        (tree / TARGET).write_text(src.replace(old, new))
        m_code, m_out = check_tree(tree, check)
        row = {"name": f"wsdyn-{name}", "repo": "Research-and-Papers/workspace-dynamics", "rev": head,
               "kind": "planted", "symptom": symptom, "tests": [TEST], "check": check,
               "base_exit": m_code, "usable": code == 0 and m_code != 0}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("name", "base_exit", "usable")}), flush=True)
    Path(__file__).with_name("p3_planted.json").write_text(json.dumps(rows, indent=2))
