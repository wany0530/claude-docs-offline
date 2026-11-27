#!/usr/bin/env bash
# CI 단위 테스트 실행기. 사용: bash ci/run_unit.sh plain|coverage
#
# 결과를 unit.log 에 남기고, 실패하면 실패한 테스트 이름과 오류 줄을 GitHub annotation(::error::)으로 내보낸다.
# GitHub 의 로그 원문은 인증 없이 읽을 수 없지만 annotation 은 공개 API 로 읽을 수 있어서,
# 이렇게 해 두면 실패 원인을 원격에서 진단할 수 있다.
set +e
mode="${1:-plain}"
if [ "$mode" = "coverage" ]; then
  python -m coverage run -m unittest discover tests -v 2>&1 | tee unit.log
else
  python -m unittest discover tests -v 2>&1 | tee unit.log
fi
status=${PIPESTATUS[0]}

if [ "$status" -ne 0 ]; then
  # annotation 은 한 단계에 10개까지 보인다: 실패/오류 줄과 Python 예외 줄을 먼저 9개, 마지막에 요약 줄
  grep -E "^(FAIL|ERROR):|^[A-Za-z_.]*(Error|Exception)\b" unit.log | head -9 | while IFS= read -r line; do
    echo "::error title=unit test failed::${line//%/%25}"
  done
  summary=$(grep -E "^(Ran |FAILED|OK)" unit.log | tr '\n' ' ')
  echo "::error title=unit test summary::${summary//%/%25}"
fi
exit "$status"
