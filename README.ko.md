# FaultDebug 한국어 안내

[English](README.md) · **한국어** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

## 설치 없이 보고서 체험

[인터랙티브 데모](https://lsh235.github.io/FaultDebugMCP/?lang=ko) · [42초 시연](https://lsh235.github.io/FaultDebugMCP/assets/demo.webm)

정상 주문·결제 SIGILL·재고 timeout의 실제 합성 테스트 기록과 native C SIGSEGV를 살펴보세요.
Linux x86_64의 로컬 Docker Engine과 Compose가 있다면 clone 후 다음 한 명령으로
8개 서비스의 세 시나리오를 직접 실행하고 보고서를 열 수 있습니다. 호스트 Python·Clang·CMake 설치는 필요 없습니다.

~~~~sh
./scripts/try-demo.sh
~~~~

출력 URL은 http://127.0.0.1:18870/index.html 입니다. Docker socket으로 자체 테스트 컨테이너를 관리하며 Ctrl+C로 보고서 서버를 종료합니다.
쇼핑몰의 기록은 계측된 C++ 경계 이벤트이며 Python 스택 전체가 아닙니다. 데모는 개발 snapshot이고 정식 릴리스가 아닙니다.
[요구 환경과 옵션](docs/showcase/README.md) · [사용 사례](docs/case-studies/payment-crash.md)

FaultDebug는 C/C++ 프로그램의 실행 중 함수 이벤트를 제한된 메모리에
기록하고, 종료 후 로컬에서 `.fault` 증거 파일을 수집·검사하는 도구입니다.
Clang/CMake 빌드 연동, Python CLI, 읽기 전용 MCP 검사기를 제공합니다.

![FaultDebug 수집 및 검사 흐름](docs/assets/faultdebug-overview.svg)

> 수집되지 않은 이벤트를 추정하지 않습니다. overflow, 불완전한 trace,
> source provenance 불일치를 결과에 드러냅니다.

## 현재 상태

현재 개발 목표는 **2.0.0a2** (`v2.0.0-alpha.2`)이며, 문서의 증거 기반 구현은
[v1.2.0-rc.2](https://github.com/lsh235/FaultDebugMCP/releases/tag/v1.2.0-rc.2)를 기준으로 합니다.
이번 메이저 후보는 기본 MCP 도구 목록을 27개에서 15개 `focused` 흐름으로 바꾸고
고급 정적 호출 관계 도구를 해당 기본 목록에서 제외합니다. 전체 27개 도구가 필요하면
`--tool-profile full`을 지정하면 되며 `get_call_relations`는 계속 사용할 수 있습니다.
정식 v2.0.0 수락은 전체 릴리스 게이트와 독립 검토가 남아 있습니다. 아래 v1.3 알파 이력은
이번 호환성 전환에 이른 개발 과정을 기록합니다.
변경 근거는 [리서치](docs/mcp-v2-major-profile-research.md),
[검토 결정](docs/mcp-v2-major-profile-review.md), [v2.0 실행 계획](docs/next-version-v2.md)에 있습니다.
첫 후보의 범위와 검증 결과는 [v2.0.0-alpha.1 기록](docs/releases/v2.0.0-alpha.1.md)에 있습니다.
현재 후보는 focused 도구 수를 늘리지 않고 한 번의 MCP 호출로 최대 32개 캡처의
count-only 요약을 비교합니다. [리서치](docs/mcp-batch-evidence-summary-research-v2.md)와
[독립 검토](docs/mcp-batch-evidence-summary-review-v2.md)를 확인하세요.
기존 프로젝트용 정적 ELF 점검과 분리된 CMake 적용 경로를 제공합니다.
`faultdebug self-test`가 설치된 경로의 고정 fixture capture를 확인하고,
알파9의 `faultdebug integrate --execute-build`는 격리된 configure/build/index/bundle 단계를 명시적으로 실행합니다.
알파10은 별도 `--execute-target` opt-in과 반복형 `--target-arg`를 추가해
앱을 실행하고 complete/stable/loss-free 캡처 하나를 검증합니다. 알파11의
`--fault-report`는 검증된 캡처와 번들로 보고서를 함께 생성합니다. 알파12는
`--fault-report-language ko`로 보고서 언어를 고를 수 있고 영어 기본값을 유지합니다.
알파13은 통합 보고서의 스레드별 표시 이벤트를 `--fault-report-max-events 1..500`으로
조절하며 기본 80개와 생략 수 표시는 유지합니다. Meson 적용은 동일한 source provenance
경로를 보장할 설계가 준비될 때까지 보류했습니다.
알파14는 `--fault-report-output PATH`로 검증된 보고서 파일의 저장 위치를 지정하며,
기존 경로는 덮어쓰지 않고 경로 생략 시 캡처 옆에 생성합니다.
알파15는 source lookup과 정적 호출 관계 도구가 실제로 요구하는 검증 번들을 MCP
스키마에서도 필수·비 nullable 값으로 표시해, 불필요한 실패 호출을 줄입니다.
알파16은 검증된 source bundle을 알 수 없을 때 후보 경로를 찾는 읽기 전용
`discover_bundles`를 추가합니다. 후보 탐색은 manifest를 검증하지 않으며 실제 검증은
source 도구가 수행합니다. 모든 실행은 명시적 opt-in입니다.
알파17은 `--tool-profile focused`를 추가해 첫 조사에 적합한 15개 MCP 도구만
노출했습니다. 당시 기본 `full` 프로필은 27개 도구를 유지했습니다. v2.0.0 후보에서는
`focused`가 기본 15개 도구가 되고, `--tool-profile full`이 전체 27개 도구를 제공합니다.
알파18은 공식 MCP Python SDK v1.30으로 올리고 capabilities, store health,
artifact/bundle discovery 네 도구에 검증 가능한 구조화 응답 스키마를 게시합니다.
기존 텍스트 응답은 유지합니다. 실제 stdio에서 두 프로필의 스키마와 응답을 검증했으며,
Glama 관리자 pin·배포·재평가와 공식 점수 변화는 확인되지 않았습니다.
알파19는 전체 27개 도구에 작업별 top-level 표시 제목을 제공하고 기존 annotation
제목과 맞춥니다. 두 MCP 프로필의 실제 stdio 정의를 검사합니다. 점수 변화는
Glama의 재평가 전까지 주장하지 않습니다.
알파20은 검증된 source 조회에 7개 필드의 구조화 응답을 추가하고 기존 텍스트 응답과
필수 bundle 검증을 유지합니다. 확장 가능한 static relation 행은 이번 스키마 범위에서
제외합니다.
알파21은 읽기 전용 incident 목록의 성공/오류 응답 스키마를 추가합니다. 더 큰 동적
incident evidence payload는 별도 검토 전까지 스키마 범위에서 제외합니다.
알파22는 full 프로필의 `list_sessions`에 6개 필드의 typed 결과를 제공합니다. focused
카탈로그 범위와 세션 도구 제외 정책은 유지합니다. 공식 Glama 점수는 재평가 전까지
확인되지 않았습니다.
알파23은 focused에도 포함된 `get_source_evidence`에 검증된 citation과 unresolved 사유,
오류를 구분하는 typed 결과를 추가합니다. 기존 텍스트 응답과 단일 citation 편의 필드는
유지하고, source 본문은 별도의 `get_function_source`로 제공합니다. Glama 재평가와 점수는
확인되지 않았습니다.
[알파24는 `get_rpc_trace`에 정규화된 관측 이벤트와 6가지 불완전성 진단을 구분하는 typed
결과를 추가합니다. 기존 텍스트 응답, 페이지 처리와 observed/static_candidates/unresolved
경계를 유지합니다. Glama 점수 상승은 공식 재평가 전까지 주장하지 않습니다.](docs/releases/v1.3.0-alpha.24.md)
[알파25는 full/focused 프로필 모두에 `get_fault_flow`의 typed 실행 흐름 결과를 추가합니다.
스레드 이벤트, crash, gap, 주소 해석과 검증된 source 표시를 구분하며 기존 텍스트 응답과
수집 동작을 유지합니다. Glama 점수 변화는 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.25.md)
[알파26은 focused 프로필의 8개 설명에서 해당 프로필에 없는 대체 도구를 안내하던 내용을
수정합니다. full 프로필의 설명과 두 프로필의 도구·스키마·실행 동작은 유지합니다.
Glama 점수 변화는 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.26.md)
[알파27은 full/focused 양쪽에 `get_incident_report`의 typed 출력 스키마를 추가해 고정된
보고서 envelope, 관측 RPC 이벤트와 페이지 메타데이터를 제공합니다. 동적 관계·후보·진단
행은 보존하며 Glama 점수 변화는 공식 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.27.md)
[알파28은 full/focused 양쪽의 `resolve_addresses` 결과를 typed 스키마로 제공합니다.
주소별 Build-ID 해석, 함수 ID, static edge와 미해결 사유를 구조화하되 해석 동작은
바꾸지 않았습니다. Glama 점수 변화는 공식 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.28.md)
[알파29는 `get_call_relations`의 고정 envelope를 full/focused 양쪽에서 typed로 게시합니다.
정적 index의 직접·미해결 relation 행과 알 수 없는 확장 필드는 보존하며, 실제 런타임 호출
증거로 표현하지 않습니다. Glama 재평가와 점수 변화는 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.29.md)
[알파30은 `get_thread_trace`의 페이지와 thread/event 결과를 typed로 게시합니다. OS thread
ID의 세대 재사용, 조건부 retention, raw address/event 값과 확장 필드를 구분하며 기존
이벤트 순서·페이지 처리·텍스트 응답은 유지합니다. Glama 재평가와 점수 변화는 확인되지
않았습니다.](docs/releases/v1.3.0-alpha.30.md)
[알파31은 `get_incident_slice`에 성공/오류 구조화 출력 계약을 추가합니다. SQLite 행 확장과
생산자 증거 payload는 열린 형태로 보존하고, 페이지·이벤트 상한 및 source reference 검증 경계를
명시합니다. Glama 재평가와 점수 변화는 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.31.md)
[알파32는 `get_evidence_summary`를 focused에도 노출해 상세 이벤트를 가져오기 전 관측 RPC/관계 수와
미해결 진단을 확인하는 count-only 단계를 추가합니다. 출력 스키마를 함께 게시하고 focused 카탈로그는
16개 도구가 됩니다. Glama 점수 변화는 공식 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.32.md)
[알파33은 `open_fault`의 안정된 native capture 필드를 타입화하고 sparse JSON과 생산자 확장 필드는
열린 형태로 보존합니다. focused의 16개 도구 모두 출력 스키마를 제공합니다. Glama 점수 변화는
공식 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.33.md)
[알파34는 `get_service_flow`의 요약과 페이지 응답에 구조화 출력 계약을 추가합니다. 일곱 수집 종류의
행과 이후 확장은 열어 두고, CLI/MCP 공통 projection과 snapshot 재검사 동작을 유지합니다. Glama 점수는
공식 재평가 전까지 확인되지 않았습니다.](docs/releases/v1.3.0-alpha.34.md)
[service-flow 출력 스키마 리서치](docs/mcp-service-flow-output-research.md) ·
[service-flow 출력 스키마 검토](docs/mcp-service-flow-output-review.md) ·
[open-fault 출력 스키마 리서치](docs/mcp-open-fault-output-research.md) ·
[open-fault 출력 스키마 검토](docs/mcp-open-fault-output-review.md) ·
[focused evidence-summary 리서치](docs/mcp-focused-evidence-summary-research.md) ·
[focused evidence-summary 검토](docs/mcp-focused-evidence-summary-review.md) ·
[incident-slice 출력 스키마 리서치](docs/mcp-incident-slice-output-research.md) ·
[incident-slice 출력 스키마 검토](docs/mcp-incident-slice-output-review.md) ·
[thread-trace 출력 스키마 리서치](docs/mcp-thread-trace-output-research.md) ·
[thread-trace 출력 스키마 검토](docs/mcp-thread-trace-output-review.md) ·
[호출 관계 출력 스키마 리서치](docs/mcp-call-relations-output-research.md) ·
[호출 관계 출력 스키마 검토](docs/mcp-call-relations-output-review.md) ·
[기존 프로젝트 적용 안내](docs/existing-project-adoption.md) ·
[보고서 언어 검토](docs/integration-report-language-review.md) ·
[이벤트 상한 검토](docs/integration-report-event-limit-review.md) ·
[보고서 경로 검토](docs/integration-report-output-review.md) ·
[MCP 번들 계약 검토](docs/mcp-required-bundle-review.md) ·
[번들 후보 탐색 검토](docs/mcp-bundle-discovery-review.md) ·
[MCP 프로필 검토](docs/mcp-profile-review.md) ·
[구조화 응답 검토](docs/mcp-output-schema-review.md) ·
[표시 제목 리서치](docs/mcp-tool-title-research.md) ·
[표시 제목 검토](docs/mcp-tool-title-review.md) ·
[source 출력 스키마 리서치](docs/mcp-source-output-research.md) ·
[source 출력 스키마 검토](docs/mcp-source-output-review.md) ·
[incident 목록 출력 스키마 리서치](docs/mcp-incident-list-output-research.md) ·
[incident 목록 출력 스키마 검토](docs/mcp-incident-list-output-review.md) ·
[session 목록 출력 스키마 리서치](docs/mcp-session-list-output-research.md) ·
[session 목록 출력 스키마 검토](docs/mcp-session-list-output-review.md) ·
[source evidence 출력 스키마 리서치](docs/mcp-source-evidence-output-research.md) ·
[source evidence 출력 스키마 검토](docs/mcp-source-evidence-output-review.md) ·
[RPC trace 출력 스키마 리서치](docs/mcp-rpc-trace-output-research.md) ·
[RPC trace 출력 스키마 검토](docs/mcp-rpc-trace-output-review.md) ·
[fault-flow 출력 스키마 리서치](docs/mcp-fault-flow-output-research.md) ·
[fault-flow 출력 스키마 검토](docs/mcp-fault-flow-output-review.md) ·
[focused 설명 리서치](docs/mcp-focused-description-research.md) ·
[focused 설명 검토](docs/mcp-focused-description-review.md) ·
[incident report 출력 스키마 리서치](docs/mcp-incident-report-output-research.md) ·
[incident report 출력 스키마 검토](docs/mcp-incident-report-output-review.md) ·
[주소 해석 출력 스키마 리서치](docs/mcp-address-resolution-output-research.md) ·
[주소 해석 출력 스키마 검토](docs/mcp-address-resolution-output-review.md) ·
[evidence summary 후보 리서치](docs/mcp-evidence-summary-output-research.md) ·
[evidence summary 후보 검토](docs/mcp-evidence-summary-output-review.md) ·
[알파28 범위와 검증](docs/releases/v1.3.0-alpha.28.md) ·
[알파27 범위와 검증](docs/releases/v1.3.0-alpha.27.md) ·
[알파26 범위와 검증](docs/releases/v1.3.0-alpha.26.md) ·
[알파25 범위와 검증](docs/releases/v1.3.0-alpha.25.md) ·
[알파24 범위와 검증](docs/releases/v1.3.0-alpha.24.md) ·
[알파23 범위와 검증](docs/releases/v1.3.0-alpha.23.md) ·
[알파22 범위와 검증](docs/releases/v1.3.0-alpha.22.md) ·
[구현 범위와 검증](docs/releases/v1.3.0-alpha.21.md)

정식 릴리스의 독립 최종 수락, 현재 revision의 전체 core/gRPC profile,
kind·새 30분 soak는 남아 있습니다. Docker 8/16/32 검증은 이번 알파 기록에 명시한
제한된 시나리오 범위입니다. 이전 revision의 PASS를 현재 코드의
수락으로 옮기지 않습니다. 과거 soak의 손실은 [기존 기록](docs/v1.2-p3-01.md)에 남겼습니다.

## 빠른 시작

지원 기준은 Ubuntu 24.04 x86_64, Python 3.12, Clang 18, CMake 3.20 이상,
Ninja입니다.

```sh
git clone https://github.com/lsh235/FaultDebugMCP.git
cd FaultDebugMCP
sudo apt-get update
sudo apt-get install clang-18 llvm-18-tools cmake ninja-build python3.12 python3.12-venv
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
cmake -S . -B build -G Ninja \
  -DCMAKE_C_COMPILER=clang-18 \
  -DCMAKE_CXX_COMPILER=clang++-18 \
  -DFAULTDEBUG_PYTHON_EXECUTABLE="$PWD/.venv/bin/python" \
  -DFAULTDEBUG_BUILD_TESTS=ON
cmake --build build --parallel 2
```

`uv`를 사용한다면 위 Python 가상환경·설치 명령을 다음 두 명령으로 바꿀 수
있습니다. Clang, CMake 등 apt로 설치한 native 도구는 여전히 필요합니다.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
```

환경을 확인하고 예제를 실행합니다.

```sh
export FAULTDEBUG_REAL_CC=clang-18
export FAULTDEBUG_REAL_CXX=clang++-18
.venv/bin/fault-debug doctor
.venv/bin/fault-debug self-test
.venv/bin/fault-debug run --artifact-dir artifacts -- build/test/fd_c_chain 16
```

`self-test`는 생성한 고정 fixture를 빌드·실행하고 임시 trace를 검사한 뒤 삭제합니다.
사용자 프로젝트 실행이나 source resolution 검증은 포함하지 않습니다.

정상 종료에서는 기본적으로 `.fault` 파일을 만들지 않습니다. SIGSEGV 수집은
다음처럼 실행합니다.

```sh
.venv/bin/fault-debug run --artifact-dir artifacts -- build/test/fd_signals 11
```

수집한 파일을 검사하려면 `.venv/bin/fault-debug inspect artifacts/fault-<pid>.fault`를
사용하세요. source 기반 분석에는 빌드에서 생성한 source bundle이 필요합니다.

장애 문서와 탐색형 실행 흐름 보고서를 생성할 수 있습니다.

```sh
.venv/bin/fault-debug fault-report artifacts/fault-<pid>.fault \
  --bundle build/bundle --output reports/incident-001 --language ko
```

`report.html`에서 장애 PC, 호출·복귀 기록, 누락 구간을 확인하고 함수를
선택하면 검증된 소스 근거를 볼 수 있습니다. `report.md`는 문서,
`report.json`은 구조화된 근거이며 HTML 문서를 인쇄해 PDF로 저장할 수도
있습니다. 스레드 선택·검색·테마 전환을 지원합니다. 기록 순서와 정적
후보만으로 원인을 확정하지 않습니다. 자세한 내용은
[보고서 안내](docs/fault-flow-report.md)를 참고하세요.

![실제 SIGILL 장애와 검증된 소스 위치를 표시한 보고서](docs/assets/fault-flow-report.png)

[N개 프로세스 쇼핑몰 장애 실험](docs/shopping-fault-lab.ko.md)으로 더 큰 규모의
실제 서비스 간 장애를 재현할 수 있습니다. 기본 8개 독립 Docker 서비스에
risk 워커를 추가하고, 동시 주문·재고 부족·결제 거절·응답 지연·실제 crash를
검사합니다. 보고서에서 실패 구간, 전파 경로, 관측된 이유와 소스를 확인합니다.

```sh
docker build -f test/shop/Dockerfile -t faultdebug-shop:dev .
.venv/bin/python test/shop/run.py --processes 16 --requests 24 --concurrency 4 \
  --scenarios success payment_decline --output build/shop-scale
```

![쇼핑몰 서비스의 결제 crash와 실제 HTTP 실패 전파](docs/assets/shopping-fault-report.png)

artifact만 읽는 Docker MCP 구성은 [컨테이너 안내](docs/mcp-container.md)를
참고하세요. 추적 빌드는 별도 native 환경에서 실행합니다.

## 증거 해석

- **관측됨:** artifact에 실제 저장된 committed runtime record입니다.
- **정적 후보:** source나 compile database에서 찾은 가능성으로, 실행 증거가 아닙니다.
- **미해결:** 누락·모호함·손실·불일치로 확정할 수 없는 결과입니다.

부모 PID, 함수 이름, trace ID, 시각만으로 프로세스 사이의 인과관계를
확정하지 않습니다. `.fault` 및 source bundle에는 민감한 코드와 경로가 들어갈
수 있으므로 공개 이슈에 올리기 전에 정리하세요.

## 더 알아보기

- [전체 README 및 명령 예제](README.md)
- [v1.2 계획과 수락 기준](docs/next-version-v1.2.md)
- [빌드 및 CTest](test/README.md)
- [기여 안내](CONTRIBUTING.md) · [보안 정책](SECURITY.md)

### 읽기 전용 서비스 증거 조회

`faultdebug service-query EVIDENCE`와 MCP `get_service_flow`로 요약과 증거
페이지를 조회할 수 있습니다. 후속 페이지에는 처음 받은 `snapshot_id`를
전달해 입력 변경을 감지합니다. [조회 계약](docs/service-query.md)과
[REA 기반 개선 계획](docs/rea-improvement-plan.ko.md),
[구현 및 검증 결과](docs/rea-implementation-results.ko.md)를 참고하세요.
