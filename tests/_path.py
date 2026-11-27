"""테스트에서 상위 폴더의 모듈을 import 할 수 있게 경로를 추가한다."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
