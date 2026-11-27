"""호환용: 실제 코드는 docsnap/fetch.py (같은 모듈 객체를 돌려주므로 import·mock·명령줄 모두 기존과 동일)."""
import sys

if __name__ == "__main__":
    import runpy
    runpy.run_module("docsnap.fetch", run_name="__main__")
else:
    import importlib
    sys.modules[__name__] = importlib.import_module("docsnap.fetch")
