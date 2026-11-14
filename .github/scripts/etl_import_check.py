"""Import every ETL module (CI check).

Imports each etl/*.py without running it (every step keeps its
work under `if __name__ == "__main__"`), which catches syntax errors, missing
imports and names that do not resolve at import time. Needs the packages in
requirements.txt, not the raw DOE/NCES files.

    python .github/scripts/etl_import_check.py
"""

import importlib.util
import sys
import traceback
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parents[2] / "etl"


def main() -> int:
    sys.path.insert(0, str(ETL_DIR))
    failed = []
    modules = sorted(p for p in ETL_DIR.glob("*.py"))
    for path in modules:
        name = "etl_" + path.stem
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except BaseException:  # SystemExit included: a module must not exit on import
            failed.append(path.name)
            print(f"FAIL {path.name}")
            traceback.print_exc()
        else:
            print(f"ok   {path.name}")
    if failed:
        print(f"{len(failed)} of {len(modules)} modules failed to import: {', '.join(failed)}")
        return 1
    print(f"All {len(modules)} ETL modules import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
