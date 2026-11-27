"""명령줄 실행용 짧은 진입점. 실제 코드는 docsnap/site/verify.py."""
import runpy

runpy.run_module("docsnap.site.verify", run_name="__main__")
