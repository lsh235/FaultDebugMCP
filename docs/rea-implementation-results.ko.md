# REA 기반 개선 구현과 검증 결과

검증일: 2026-10-16. 기준 revision: `d97177fb7d9ed5f97a6c1a98ef8b3dcc37a65492`.
작업 브랜치: `feat/rea-evidence-foundation`.

## 구현 결과

[개선 계획](rea-improvement-plan.ko.md)의 실행 묶음 A–D를 구현하고 검증했다.
E의 검토 제출과 문서 전달을 이 변경에 포함한다. 장기 프로그램 F–J는 계획 상태다.
프로젝트의 기존 v1.2 stable 최종 수락과 v1.3 로드맵을 완료했다고 선언하지 않는다.

- **정확성**: session/process/generation/trace hi/trace lo/rpc 전체 키를 사용한다.
  caller end, receiver end, symptom, failure status가 같은 범위를 사용한다.
  잘못된 generation의 native event는 보강 근거에서 제외한다. optional hi=0으로
  legacy log를 유지하며 bool ID와 잘못된 타입은 거부한다.
- **미확인 상태**: 종료 이벤트 누락·중복을 명시하고 status 부재를 성공으로
  채우지 않는다. end<begin이면 duration을 생성하지 않고 gap을 남긴다.
- **입력 비용**: 16MiB/file, 64MiB 합계, 64 captures, 256 evidence files,
  4096 scan entries, 100,000 application lines를 적용한다. 잘못된 행도 비용에
  포함한다. regular-file/no-follow/nonblocking open으로 FIFO 대기를 방지한다.
- **조회**: CLI `service-query`와 MCP `get_service_flow`가 하나의 query 함수를
  호출한다. summary와 7개 collection, page 1–200, 응답 JSON 1MiB, 입력 hash 기반
  snapshot 검증을 추가했다. snapshot은 실제 입력 byte의 fingerprint이며 live
  filesystem transaction이나 cache가 아니다.
- **유지보수**: native/app event 색인을 한 번 구축해 관계마다 전체 event를 다시
  찾는 작업을 줄였다. capabilities, CI, CMake identity gate, README와 사용 계약을
  갱신했다. runtime ABI/FDAR/store schema와 기존 required MCP 도구는 유지했다.

## 수정 전 재현과 수정 후 확인

기존 `service_report_test.py` 14개는 수정 전 통과했다. 새로운 반례에서는
상위 trace ID만 다른 app log가 native 호출에 연결됐고, generation 2의 client_end가
generation 1 호출에 status/duration을 공급했다. 음수 시간 차가 duration으로
표시되고, 중복 end의 미확인 사유가 빠지는 것도 확인했다.

이 반례를 수정한 뒤 독립 기대값을 사용하는 identity 테스트 8개가 통과했다.
테스트 입력은 직접 만든 FDAR fixture이며 실제 instrumented process를 실행한
검증과 구분한다. source/runtime 관련 전체 release acceptance의 대체물이 아니다.

## 실행한 검증

| 명령 또는 검사 | 결과 | 확인 범위 |
| --- | --- | --- |
| `python test/service_identity_contract.py` | PASS 8개 | full trace, generation, bool/type, missing/duplicate end, negative time |
| `python test/service_report_test.py` | PASS 14개 | 기존 서비스 보고서와 native join 회귀 |
| `python test/service_query_contract.py` | PASS 10개 | page union, 이동/변경/추가/삭제, byte/file/line/scan 예산, FIFO/symlink, CLI와 실제 MCP parity, read-only |
| `python test/fault_report_test.py` | PASS 14개 | 기존 fault flow와 read-only MCP 회귀 |
| `python test/mcp_tool_metadata.py` | PASS | 실제 stdio 도구 26개, 설명 있는 parameter 81개, invalid call 12개 거부, 증거 파일 불변 |
| `python test/index_linkage.py` | PASS | 상대 compilation database/source indexing 회귀 |
| `python -m compileall -q faultdebug ...` | PASS | Python 구문 컴파일 |
| `python -m build --sdist --wheel` | PASS | sdist와 wheel 생성 |
| 별도 venv에 wheel 설치 후 `/tmp`에서 CLI/MCP 호출 | PASS | checkout 밖 site-packages 로딩 확인, service summary 동등성 |
| `python -m pip check` | PASS | 설치 dependency 선언 충돌 없음 |
| `git diff --check` | PASS | 공백/patch 기본 검사 |

위 네 unittest suite 합계는 46개다. metadata audit의 invalid call 12개는 이 합계와
별도다. 의존성은 pyproject의 Python 3.12, MCP 1.9.4, libclang 18.1.1,
pyelftools 0.31 제약으로 설치했다. 설치된 Pydantic은 2.13.5다. MCP 초기화 때
upstream pydantic-settings의 `lifespan` forward-reference 경고가 출력됐으나 실제
stdio 호출은 통과했다. 경고를 숨기거나 완전한 dependency compatibility 증명으로
해석하지 않았다.

## 10만 행 비용 측정

재현 명령: `python test/service_query_benchmark.py`.

동일 프로세스에서 새 임시 frozen directory를 만들고, 두 native FDAR fixture와
정확히 100,000 application rows를 읽는 summary query를 5회 실행했다.
추가 행은 같은 정상 identity의 `note`이며 native recording이나 대규모 실제
서비스 실행이 아니다. 기대 event=100,000과 observed call=1을 독립적으로 확인한다.

| 항목 | 관측값 |
| --- | --- |
| 입력 byte | 27,200,993 |
| 5회 wall time 초 | 3.9294 / 4.1869 / 3.5100 / 3.8124 / 3.3344 |
| 중앙값 초 | 3.8124 |
| 프로세스 peak RSS KiB | 196,732 |
| pretty JSON summary byte | 826 |
| evidence files | 12 |

OS page cache를 비우지 않았으며 cold filesystem latency가 아니다. peak RSS는
fixture 생성과 반복 전체를 포함한 프로세스 최대값이다. 고정 4-vCPU/8GiB runner의
p95나 production SLA, 32-service 성능을 뜻하지 않는다. 본 결과는 후속 규모
측정의 출발점이며 snapshot 매 페이지 재계산 비용은 남아 있다.

## 실행하지 않은 수락 항목

- 공식 Clang 18 native build/runtime/gRPC gate: 현재 환경에 compiler/fixture
  toolchain이 없으며 이번 변경에서 native 코드를 수정하지 않아 NOT RUN.
- Docker shopping N=8/16/32, Kubernetes kind, 1800초 soak: NOT RUN.
- 실제 외부 libuv 재평가, W3C header propagation, retry durable ledger: NOT RUN.
- hosted GitHub Actions와 독립 최종 release audit: 이 문서의 로컬 검증 범위에
  포함하지 않는다. PR 이후 실제 workflow run과 commit을 확인해야 한다.

## 호환성과 남은 과제

기존 application schema=1에서 `trace_id`는 유지하고 hi는 optional이다. 기존보다
엄격해진 타입·directory/file/line/byte 제한은 의도된 입력 계약 변경이다. malformed
입력을 정상 성공으로 유지하는 호환성은 제공하지 않는다. directory에 unrelated
symlink가 있으면 읽기를 거부하므로 전용 frozen evidence directory를 사용한다.

현재 파일별 hash는 읽은 byte를 증명하지만 서로 다른 파일의 원자적 동시 시점을
보장하지 않는다. 입력을 동결해야 한다. output byte 제한은 JSON payload에 적용되며
JSON-RPC framing byte 자체를 포함한 transport 예산은 아니다. application 원인은
계속 자기 보고이며 hash는 authenticity를 증명하지 않는다. attempt 기반의 일반적인
retry pairing과 clock-domain provenance는 후속 F 단계에서 구현해야 한다.

이번 결과를 다음 프로젝트에 적용할 때는 먼저 증거 identity를 정하고, unknown을
표현한 뒤, transport 공통 조회와 실제 protocol 회귀를 만든다. 그 다음 대표 workload
비용을 측정하고 필요한 경우에만 cache/provider/원격 기능을 추가한다.
