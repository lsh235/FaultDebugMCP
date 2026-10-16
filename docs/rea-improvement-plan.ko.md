# FaultDebugMCP 개선 계획 — REA의 발전 과정에서 가져올 설계 원칙

작성일: 2026-10-16 (Asia/Seoul)

## 1. 목표와 고정 기준

목표는 도구 수나 코드량을 늘리는 것이 아니라, 실제 장애 분석에서 잘못된 원인을 만들지 않고 반복 가능한 근거를 빠르게 제공하는 프로젝트로 발전시키는 것이다. 이번 계획은 조사 → 오류 재현 → 수정 → 공통 조회 → 외부 계약 검증 → 검토 가능한 변경 제출 순으로 실행한다. 이번 실행 묶음 A–E와 장기 프로그램 F–J를 구분한다. 장기 프로그램의 계획 작성은 구현 완료를 뜻하지 않는다.

- FaultDebugMCP 기준: `d97177fb7d9ed5f97a6c1a98ef8b3dcc37a65492`, 기본 브랜치에서 도달 가능한 공개 커밋 19개, Python 패키지 `1.2.0rc1`.
- REA 분석 기준: `d72d856f58d4747c5eb4307426e80d20934e017c`, main 조상 3,402개와 태그 36개를 비교한 앞선 보고서.
- 기존 계획: `docs/next-version-v1.3.md`, `docs/next-version-v1.2.md`, `ROADMAP.md`. 기존의 미완료 stable 수락을 이번 작업으로 대신 선언하지 않는다.
- 조사 방식: 실제 소스·테스트·Git 기록을 직접 읽었다. AGENTS.md가 지정한 codebase-memory는 현재 제공 스킬/플러그인에서 찾지 못했다. 따라서 그래프 인덱스 전체 탐색을 완료했다고 주장하지 않는다.
- 시작 시 검증: `python3 test/service_report_test.py` 14개 PASS. 기존 통과가 새 경계 사례의 정확성까지 보증하지는 않는다.

## 2. 현재 강점과 개선할 정확한 경계

이미 C11 native recorder, FDAR checksum, 빌드/소스 provenance, 검증된 bundle, 별도 application evidence, SQLite store, CLI/MCP, 설치 검증과 장애 fixture가 있다. 재작성보다 이 경계들의 계약을 강화하는 것이 효과적이다. runtime ABI나 저장소 schema를 무조건 바꾸면 과거 증거를 읽는 비용이 커지므로 이번 실행은 Python 분석/조회 계층의 호환 가능한 확장에 집중한다.

| 관찰된 위치 | 현재 동작/위험 | 이번 조치 | 확인할 결과 |
| --- | --- | --- | --- |
| `faultdebug/service_report.py` spans 및 call join | native 관계는 trace hi/lo를 사용하지만 app join은 lo/rpc만 사용. 다른 trace가 보강 증거처럼 표시될 수 있음 | hi/lo와 session/process/generation을 함께 사용 | hi만 다른 app log는 원인·status를 보강하지 않음 |
| 같은 파일의 begin/end/symptom join | process_id는 비교하지만 generation 조건이 일부 누락 | 전체 endpoint identity와 trace/rpc를 공통 키로 사용 | 재시작 전후 event/status/duration이 섞이지 않음 |
| 같은 파일의 `_bounded`/rglob | 파일당 16MiB만 제한; 입력 개수·총량·잘못된 행 전체 처리 예산이 불충분 | 총 byte/file/scan-entry/line 예산과 regular-file 확인 | 큰 입력·FIFO·symlink·손상 행 폭주를 명시적으로 거부 |
| 같은 파일의 관계별 events 전체 순회 | 각 relation마다 여러 번 모든 app event를 검색 | endpoint/trace/rpc/kind 색인을 한 번 생성 | 의미를 보존하며 반복 전체 탐색 제거 |
| `cli.py`, `mcp_server.py` | offline service-report는 있으나 read-only service query 없음 | 같은 query 함수를 두 진입점에서 호출 | CLI와 실제 MCP stdio의 결과 일치 |
| 페이지 조회 | 매 요청 입력 파일이 바뀌면 다른 결과의 페이지를 섞을 수 있음 | 입력 manifest 기반 snapshot ID와 기대 ID 검증 | 변경된 입력에 이전 snapshot을 주면 오류 |
| `.github/workflows/ci.yml` | 기존 report/metadata 테스트는 있음 | 새 negative/query/stdio 회귀를 같은 CI에 연결 | 실패하면 PR gate 실패, 누락을 성공 처리하지 않음 |

## 3. REA에서 가져올 것과 도입 조건

| REA의 실제 발전 | FaultDebugMCP 적용 | 도입 비용/피할 과잉 설계 |
| --- | --- | --- |
| CLI/MCP 공통 application runtime (`97541d8da`) | 서비스 조회의 의미·페이지·오류·snapshot 계산을 순수 Python 함수 한 곳에 둔다 | 범용 DI framework나 모든 CLI 재작성은 필요 없음 |
| evidence/provenance와 canonical Evidence (`63bf91405`) | observed native endpoint, application self-report, unresolved를 유지하고 입력 hash를 공개 | 하나의 confidence 점수로 다른 증거 종류를 합치지 않음 |
| target/snapshot identity | session/process/generation + 전체 trace ID + RPC 범위로 결합 | PID/서비스 이름만으로 join하지 않음 |
| 보존 결과와 선택 조회 (`db675f1d5`) | 전체 offline 보고서를 유지하고 summary/collection 페이지를 제공 | 이번에는 캐시를 만들지 않고 매번 재검증. 비용 측정 후 retained cache 검토 |
| unknown/false/absence 분리 | unmatched end/status, clock domain 부재, 손실을 unresolved로 표시 | cause가 없다고 정상이라고 판단하지 않음 |
| 공통 process supervision (`70e1a0f53`) | 후속 collector/agent 작업에 자원 소유자·deadline·cleanup 결과를 명시 | 이번 read-only 조회에 불필요한 프로세스 계층 추가 금지 |
| v4 replay DSL 제거 (`e07b81649`) | 기존 runner와 fixture에 회귀 추가, 새로운 workflow DSL 미도입 | 분석 도구마다 다른 정책/재현 언어를 만들지 않음 |
| 실제 task 비용 측정 | input bytes, output bytes, wall time, peak RSS, false corroboration을 별도로 측정 | JSON byte 수를 token 수 또는 실제 LLM 성능으로 오해하지 않음 |

REA 커밋 링크: https://github.com/morluto/rea/commit/97541d8da · https://github.com/morluto/rea/commit/63bf91405 · https://github.com/morluto/rea/commit/db675f1d5 · https://github.com/morluto/rea/commit/70e1a0f53 · https://github.com/morluto/rea/commit/e07b81649

## 4. 이번에 실행하는 작업 묶음 A–E

### A. 증거 결합의 정확성

공통 키는 `(session_id, process_id, process_generation, trace_id_hi, trace_id_lo, rpc_id)`다. 기존 application schema=1의 `trace_id`는 low 64비트로 유지하고 `trace_id_hi`가 없으면 0이다. 명시된 hi는 unsigned 64비트 정수여야 한다. bool은 int처럼 수락하지 않는다. legacy 입력은 hi=0인 native trace에만 대응한다.

call label, caller end, symptom, receiver end, failure status에 동일한 범위를 적용한다. 관계를 만든 native process_relations와 label join의 조건이 달라서는 안 된다. retry/attempt를 완전히 지원한다고 주장하지 않는다. 같은 범위에서 begin/end가 여러 개면 명시적으로 ambiguous/unresolved이며 임의의 하나를 선택하지 않는다. duration은 같은 endpoint의 timestamp에서만 계산하며 end<begin이면 숫자를 생성하지 않는다. 서로 다른 프로세스의 monotonic 순서로 causal order를 만들지 않는다.

완료 기준: 정상 legacy fixture 유지, hi 충돌, 재시작 세대 충돌, bool identity, 중복 end, 음수 시간의 독립 fixture에서 false corroboration=0. 원래 코드에서 새 negative case가 실패하는 재현 기록을 남긴다.

### B. bounded evidence reader

기본 정책: 파일당 16MiB, native capture 64개, evidence 파일 합계 256개, 합계 64MiB, directory entry scan 4096개, application JSONL 물리 행 100,000개. 이 값은 무한 입력을 안전하게 처리한다는 의미가 아니라 명시적 초기 운영 예산이다. 모든 파일/행은 valid event가 아니더라도 비용 예산에 포함한다. 초과하면 부분 성공으로 잘라내지 않고 오류를 반환한다.

최종 경로의 regular-file 검사와 no-follow open, directory symlink 거부, bounded directory traversal을 사용한다. 증거 폴더는 수집 종료 후 동결된 로컬 입력으로 취급한다. adversarial concurrent filesystem 변경까지 완전한 트랜잭션 스냅샷을 제공한다고 주장하지 않는다. bundle 검증의 별도 비용도 숨기지 않는다.

완료 기준: 총량/개수/잘못된 행 초과, symlink와 FIFO, 손상 native artifact, 누락 입력에 대한 테스트. byte 예산 테스트는 낮춘 상수로 경계 동작을 확인하고 대용량 실제 성능 측정과 구분한다.

### C. 공통 서비스 조회

새 `faultdebug service-query EVIDENCE --section summary|services|calls|causes|events|native_relations|unresolved|evidence_files --page N --page-size N --snapshot-id ID`와 MCP `get_service_flow`를 같은 함수에 연결한다. 기존 service-report와 MCP 도구는 유지한다. 페이지 크기 1–200, 응답 JSON 최대 1MiB. summary는 count만 제공하며 전체 evidence arrays를 몰래 포함하지 않는다.

반환 계약: schema, snapshot_id, session_id, section, total/returned/page/page_size/next_page, items, collection counts, limitations. summary는 count와 limitations만. 각 collection을 명시적으로 요청하므로 observed/native/app/unresolved를 한 의미의 목록으로 섞지 않는다. MCP는 root allowlist 아래 directory만 읽고 파일/DB를 쓰지 않는다. CLI는 사용자 지정 로컬 directory를 읽는다.

snapshot ID는 상대 경로·입력 SHA-256·종류·byte 길이의 정렬 manifest와 query contract version에서 계산한다. page 번호와 절대 root 경로는 포함하지 않는다. 첫 요청에서 받은 ID를 다음 요청에 전달한다. 입력 변경 시 자동 재시작하거나 새 입력으로 계속하지 않고 오류를 낸다. 이번 query는 bundle 인수를 받지 않아 source enrichment가 snapshot 밖에서 바뀌지 않는다. source가 필요하면 기존 verified bundle 기반 도구를 사용한다.

완료 기준: page union=전체 결과, out-of-range는 빈 page/next_page=null, invalid page는 오류, 동일 byte를 다른 directory에 복사해도 동일 snapshot, byte 변경/파일 추가·삭제로 snapshot 달라짐, 구 snapshot 거부, CLI/MCP payload 일치, 조회 전후 파일 hash와 목록 불변.

### D. 계약/CI/패키지 검증

native runtime 변경이 없더라도 관련 Python regression, 실제 MCP initialize/tools/list/tools/call, wheel build와 checkout 밖 consumer를 검증한다. 새 도구의 각 parameter 설명과 readOnly annotation을 schema 수준에서 확인한다. required 도구 목록은 그대로 유지하고 additional_tools에 새 도구를 추가한다. 새 한계를 capabilities에 공개한다.

CI에 빠른 identity/budget/query/stdio 테스트를 연결한다. 실제 runtime/Clang18/gRPC/soak가 없는 환경에서는 NOT RUN으로 기록한다. GCC build나 mock을 공식 Clang18 release gate로 대체하지 않는다. 이 변경만으로 stable 1.2.0 또는 1.3.0을 발행하지 않는다.

### E. 결과와 검토 단위

문서에 수정 파일, 실행 명령, 성공/실패/미실행, 호환성, 남은 위험을 기록한다. 분리 브랜치에서 commit하고 검토 가능한 draft PR로 제출한다. main 병합과 stable release는 별도 수락 작업이다. 재현용 테스트는 저장소에, 개발 환경 로그/빌드/가상환경은 추적 제외한다.

## 5. 후속 프로그램 F–J와 진입 조건

| 단계 | 작업 | 선행 조건 | 완료 기준/산출물 |
| --- | --- | --- | --- |
| F: identity transport | 기존 v1.3 P1-01/02의 W3C traceparent adapter, host boot/clock domain, process/container generation | A의 join contract 고정 | 전체 128bit 보존, invalid header 거부, client/server span과 rpc_id 매핑, clock domain unknown 명시; ABI compatibility matrix |
| G: 실제 장애/복구 | Docker delay/reset/응답 유실/restart, SQLite fixture ledger, retry와 compensation | F | caller failure와 receiver mutation 분리, 동일 주문 durable mutation 1회, 복구 대조군, false edge=0 |
| H: 분석 규모와 retained snapshot | 8/16/32 participant, 100k event, report/query 비용 비교, 필요할 때 durable index | B–D와 대표 workload | 고정 runner에서 p50/p95 wall/RSS/output bytes 공개. cache는 입력 hash·계약버전 키, eviction/ownership/TTL 명시 |
| I: 실제 사용성 | 범용 topology와 generation filter, evidence ID→근거 drill-down, EN/KO, 키보드/인쇄 | G/H | shopping 고정 역할 밖 fan-out/fan-in/retry fixture, 32 participant 개별 선택, 모든 표시 edge 근거 조회 |
| J: 배포 수락 | 기존 v1.3 kind lifecycle/export, installed wheel/sdist, pinned 외부 corpus, soak | F–I | required FAIL=0/NOT RUN=0, hosted run URL과 revision 일치, 독립 수락 후 RC→stable |

F–J는 수일/수주가 필요한 검증 프로그램이며 미확인 환경을 성공으로 간주해 한 번에 출시하지 않는다. 기간은 F schema spike와 H runner 측정 이후 산정한다. Kubernetes는 local kind 검증과 multi-host 지원을 구분하고, OTel Demo는 기존 계획처럼 별도 experimental profile이다.

## 6. 구조와 책임

`recorder → FDAR decode → validated evidence → semantic report → query projection → CLI/MCP`를 기본 흐름으로 유지한다. evidence reader는 파일·byte 비용, service_report는 결합 의미, service_query는 snapshot/page/response budget, CLI/MCP는 사용자 입력과 transport만 책임진다. 외부 LLM은 증거 해석의 소비자이며 새로운 사실의 원천으로 취급하지 않는다.

새 provider가 실제로 두 개 이상이고 소유권/실행 계약이 겹칠 때 provider protocol을 검토한다. REA처럼 많은 provider가 없는 현재에 범용 플러그인 registry를 선제 도입하지 않는다. 오류는 기존 ValueError/MCP tool error와 호환시켜 도구별 예외 framework를 늘리지 않는다.

## 7. 품질 지표와 독립 oracle

- 정확성: 다른 trace/세대/endpoint로 인한 false corroboration=0, missing evidence의 확정 원인 승격=0.
- 완전성: 입력 손실/미확인 필드를 유지하고, 페이지 누락을 total/next_page로 확인. 빈 결과는 정상 증거가 아니다.
- 결정성: 동일 frozen input/contract/version → 동일 snapshot/조회 결과. path 이동이 분석 identity를 바꾸지 않는다.
- 비용: cold report/query wall time, 입력 byte/행 수, output bytes, peak RSS를 따로 기록. p95는 충분한 반복 수와 측정법이 있어야 주장한다.
- 운영: checkout 밖 wheel consumer와 실제 MCP stdio가 통과. CI PASS와 local PASS를 혼동하지 않는다.
- 채택성: 처음 사용자가 설치→doctor→capture→summary→source citation까지 수행하는 task completion을 외부 fixture로 검증한다.

oracle는 analyzer output에서 정답을 추출하지 않는다. synthetic fixture는 기대 process/trace/status를 직접 지정하고, 실제 장애는 native PC/signal/raw checksum과 외부 source verifier를 사용한다. 반복 코드 분기 확인만 하는 테스트 대신 관측 의미와 외부 계약을 확인한다.

## 8. 호환성·마이그레이션·되돌리기

기존 `trace_id`를 rename하지 않고 optional hi를 추가한다. runtime ABI v1, FDAR v1, store schema v2, 기존 required MCP tools를 유지한다. 이전보다 엄격한 입력 예산/파일 제한은 의도된 동작 변경이다. 큰 폴더는 session 단위로 분할하거나 별도 규모 검증을 거쳐 예산을 재설계한다. silently truncate하지 않는다.

새 조회는 read-only이므로 데이터 migration/rollback이 필요 없다. 문제가 발견되면 query 도구 등록과 CLI command를 제거할 수 있지만 identity 정확성 수정은 별도로 검토한다. stable 승격 전에 legacy capture fixtures와 실제 installed consumer 결과를 함께 확인한다.

## 9. 출처와 검증 한계

FaultDebug 기준 소스: https://github.com/lsh235/FaultDebugMCP/tree/d97177fb7d9ed5f97a6c1a98ef8b3dcc37a65492

REA 기준 소스: https://github.com/morluto/rea/tree/d72d856f58d4747c5eb4307426e80d20934e017c

핵심 대조 파일: `faultdebug/service_report.py`, `faultdebug/rpc.py`, `faultdebug/mcp_server.py`, `faultdebug/capabilities.py`, `test/service_report_test.py`, `test/mcp_tool_metadata.py`, `.github/workflows/ci.yml`, `docs/next-version-v1.3.md`. 기존 README/ROADMAP의 PASS 기록은 이전 작성자의 검증 기록이며 이번 실행 결과는 별도 실행 보고서에만 기록한다. Git 커밋 수는 프로젝트 가치나 과거 비공개 개발량의 지표가 아니다.
