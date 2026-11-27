"""명령줄 실행용 짧은 진입점. 실제 코드는 docsnap/build.py."""
import runpy

runpy.run_module("docsnap.build", run_name="__main__")
