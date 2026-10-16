# 기존 개발 프로젝트 적용을 위한 비교 조사

조사일: 2026-10-13 (Asia/Seoul). 저장소 기준: `d97177f`에서 조사한 기존 기능. 웹 사실은 아래의 공식 문서와 공식 저장소를 직접 확인했다. `master`와 `latest` 문서는 변경될 수 있으며, 외부 실행 검증용 버전은 별도로 고정했다.

이 문서는 **설계 근거와 검증 계약**이다. 비교 도구의 문서 확인을 해당 도구의 로컬 실행 성공으로 해석하지 않는다. 구현 및 실제 외부 프로젝트 실행 결과는 별도의 검증 보고서에서 판정한다.

## 결론과 이번 구현 결정

기존 프로젝트에 바로 적용하려면 먼저 바이너리를 검사하여, 이미 계측된 프로그램은 실행 경로를 안내하고 비계측 프로그램은 원본과 분리된 재빌드 경로를 만들어야 한다. 이번 경로는 선택한 타깃과 명시한 configure 옵션으로 새 빌드를 준비한다. 기존 CMake cache, presets 또는 compiler 설정을 자동 발견·복제하는 기능은 포함하지 않는다.

이번 작업은 관리자가 다음 범위를 구현 작업자에게 위임했다.

1. 기존 ELF의 읽기 전용 `preflight`: 함수 hook, runtime 의존성, Build-ID, 디버그 정보와 정적 검사 제한을 보고한다.
2. CMake 프로젝트를 위한 분리 빌드 계획: 생성한 include를 `CMAKE_PROJECT_INCLUDE`로 주입하고 `cmake_language(DEFER)`로 명시한 타깃에 기존 계측 helper를 적용한다. 필요한 compiler·빌드 옵션은 `--cmake-arg`로 명시한다.
3. `integrate`의 준비 단계에서 검토 가능한 JSON 및 shell 안내를 작성한다. 계획 생성과 실제 configure/build/index/bundle/run을 구분한다.

위 항목은 **진행 결정**이며, 이 연구 문서만으로 구현 완료나 출시 준비를 주장하지 않는다. 아래 표의 프로젝트·컴파일 DB 발견, 기존 cache 자동 보존, 분리 debug ELF 검증과 무재빌드 tracing backend는 후속 제안이다.

## 비교 대상과 공식 근거

| 프로젝트 | 기존 바이너리 지원과 재빌드 조건 | 온보딩 방식 | FaultDebugMCP에 적용할 점 |
| --- | --- | --- | --- |
| uftrace | 일반 함수 추적은 `-pg` 또는 `-finstrument-functions`로 계측해 빌드한다. x86_64/AArch64의 full dynamic tracing은 Capstone을 이용한 함수 진입부 분석 및 patching으로 재컴파일을 피할 수 있으나 patch 가능 여부와 심볼 조건이 있다. 이미 실행 중인 프로세스 attach는 README에서 지원하지 않는다고 명시한다. | `uftrace record`로 대상 실행. 함수 선택, 제외, 별도 symbol 경로를 명시한다. | 비계측 바이너리와 계측 바이너리의 사전 판별이 필요하다. 동적 patching을 구현하지 않은 현재 runtime을 uftrace의 full dynamic tracing과 동등하게 설명할 수 없다. [공식 README](https://github.com/namhyung/uftrace/blob/master/README.md), [record 매뉴얼](https://github.com/namhyung/uftrace/blob/master/doc/uftrace-record.md) |
| Linux uprobes / perf | 사용자 ELF·공유 라이브러리의 특정 파일 offset에 uprobe/uretprobe를 설치한다. 애플리케이션 재빌드 없이 probe를 설치할 수 있지만 kernel의 `CONFIG_UPROBE_EVENTS` 지원과 tracing 접근 조건이 필요하다. | kernel 인터페이스는 `PATH:OFFSET`; perf는 `-x` 대상과 함수·offset을 받는다. 로컬 변수와 소스 위치를 이용하려면 debuginfo가 필요하다. | 기존 ELF에 함수 이벤트를 얻는 별도 기술 경로는 존재한다. 그러나 권한, probe 위치, 대상 binary 식별과 이벤트 손실을 검증해야 하므로 이번 CMake 온보딩 개선으로 구현됐다고 볼 수 없다. [kernel 공식 문서](https://docs.kernel.org/trace/uprobetracer.html), [perf 공식 매뉴얼 원문](https://github.com/torvalds/linux/blob/master/tools/perf/Documentation/perf-probe.txt) |
| bpftrace | `uprobe:binary:func`, 함수 내부 offset, 명시적 offset, `uretprobe`를 지원한다. 0.26 문서는 DWARF를 이용한 소스 위치 probe와 인자 접근도 설명한다. C++ 인자의 register 위치는 ABI 영향이 있으며 `uretprobe`의 return address 교체가 일부 언어 runtime과 충돌할 수 있다. | probe 목록을 확인하고 범위를 지정한 script를 실행한다. 기본적으로 모든 probe attach가 성공해야 하며 실패 처리 정책을 별도로 바꿀 수 있다. | 정확한 지원 범위와 실패를 표시하는 계약이 필요하다. broad wildcard 자동 계측보다 선택한 함수·모듈만 검증하는 후속 backend가 적절하다. [공식 0.26 language 문서](https://bpftrace.org/docs/release_026/language) |
| Sentry Native / Symbolicator | Native SDK는 CMake로 빌드하고 앱에서 `sentry_init()` 등으로 초기화한다. 따라서 일반 SDK 통합에는 링크·초기화 변경과 재빌드가 필요하다. crashpad/native backend의 out-of-process handler는 앱과 함께 배치한다. Symbolicator는 ELF와 별도 debug 파일을 Build-ID 기준으로 찾는 경로를 명시한다. | SDK, handler 배치, 저장 경로, 디버그 심볼 관리를 구분한다. Native crash 보고와 함수 호출 이력은 서로 다른 증거다. | runtime 발견, 실행 가능한 handler/runtime 경로, 원본 binary와 심볼의 식별 검증을 별도 진단해야 한다. Build-ID가 없는 파일을 일치한다고 추정하지 않는다. [Native 공식 README](https://github.com/getsentry/sentry-native/blob/master/README.md), [Symbolicator 공식 식별 규칙](https://github.com/getsentry/symbolicator/blob/master/docs/advanced/symbol-server-compatibility.md) |
| CMake | 설치된 Config package와 imported target을 통해 기존 프로젝트에 dependency를 연결할 수 있다. `CMAKE_EXPORT_COMPILE_COMMANDS`는 Makefile/Ninja generator에 구현돼 있고 다른 generator는 무시한다. `UNITY_BUILD` 조합도 제한을 명시한다. | `find_package`와 타깃별 연결. `CMAKE_PROJECT_INCLUDE`는 `project()` 마지막 단계의 외부 include를 제공하고, `DEFER`는 현재 디렉터리 처리 종료로 호출을 미룬다. | 기존 compiler/cache를 교체하지 않고 선택한 타깃만 연결한다. `project()` 실행 시 아직 타깃이 없으므로 deferred 적용이 필요하다. 지원하는 CMake 버전·generator와 기존 include 충돌을 검사한다. [packages 공식 문서](https://cmake.org/cmake/help/latest/manual/cmake-packages.7.html), [compile DB 공식 문서](https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html), [project include](https://cmake.org/cmake/help/latest/variable/CMAKE_PROJECT_INCLUDE.html), [deferred calls](https://cmake.org/cmake/help/latest/command/cmake_language.html#deferring-calls) |
| Bear / Clang compilation database | Bear는 build command 실행 중 compiler invocation을 기록하여 `compile_commands.json`을 만든다. 빌드 로그·dry-run parsing도 현재 README에 안내되어 있다. compilation database는 원래 계측이 없던 binary에 이벤트를 추가하지 않는다. | build system의 native export를 먼저 사용하고, Make/Autotools/custom build에는 `bear -- <build-command>`를 사용한다. Clang 규격은 `arguments`를 권장하며 각 entry의 `directory`를 기준으로 해석한다. | compdb를 발견하거나 얻는 방법을 제시하되 자동 build 실행과 구분한다. 빈 incremental build에서 확보한 DB를 전체 소스의 증거로 취급하지 않는다. [Bear 공식 README](https://github.com/rizsotto/Bear), [Clang 공식 규격](https://clang.llvm.org/docs/JSONCompilationDatabase.html) |

### 비교에서 유지해야 할 기술 경계

uftrace의 full dynamic tracing과 uprobe는 **새로 활성화한 관측 경로**다. 아무런 관측 장치도 없던 이전 실행의 함수 이벤트를 사후에 복원하는 기술로 설명하지 않는다. 또한 현재 FaultDebug runtime library를 preload하거나 검색 경로에 추가하는 것만으로 원래 hook 호출이 없는 함수의 ENTER/EXIT가 생기지 않는다. 이는 위 도구들의 동적 patching/probe 동작과 구별해야 하는 구현상 추론이다.

Sentry의 debug identifier는 형식에 따라 Code ID와 다른 표현일 수 있다. ELF 관련 기능을 추가할 때 원본 GNU Build-ID 바이트와 Sentry/Breakpad 변환 표현을 하나의 문자열로 혼용하지 않는다. [공식 Symbolicator 식별 규칙](https://github.com/getsentry/symbolicator/blob/master/docs/advanced/symbol-server-compatibility.md)

## 현재 저장소의 재사용 가능 지점과 부족한 부분

구조 탐색에는 설치된 `codebase-memory` skill 지침을 읽었다. 관리자가 graph/index/coverage tool의 callable 부재를 확인했으므로 **graph/index coverage: NOT RUN**이다. 아래 사실은 지정된 파일을 직접 읽은 좁은 source fallback이며 저장소 전체의 완전한 구조 분석을 주장하지 않는다.

| 확인한 기존 기능 | 직접 확인한 소스 | 이번 개선에서의 의미 |
| --- | --- | --- |
| `run`은 instrumented target을 실행한다고 CLI help에 명시한다. 실행기는 runtime 후보 위치를 찾고 `LD_LIBRARY_PATH` 및 공유 메모리·ready FD를 설정한다. | `faultdebug/cli.py`, `faultdebug/run.py` | 설치환경 doctor와 구분되는 대상 binary preflight를 추가하여 runtime 미연결·비계측 프로그램을 실행 전 안내할 수 있다. |
| 설치·compiler·wrapper·runtime library를 검사하는 doctor가 있다. | `faultdebug/doctor.py` | 설치 검사를 재구현하기보다 프로젝트/ELF 입력 진단을 추가한다. |
| compiler wrapper는 compile step에 `-finstrument-functions`를 넣고 runtime을 링크한다. | `scripts/faultdebug-cc`, `scripts/faultdebug-cxx` | 새 안내가 wrapper로 compiler cache를 강제로 교체하지 않도록 한다. 기존 compiler와 launcher의 호환 여부를 별도로 검증한다. |
| 설치 Config package와 기존 타깃용 `faultdebug_instrument_existing` helper가 있다. | `cmake/faultdebugConfig.cmake.in`, `cmake/FaultDebugLegacy.cmake` | helper를 재사용하면서 원본 CMakeLists를 수정하지 않는 외부 include 경로를 제공한다. 선택한 타깃은 계측 flags가 바뀌므로 별도 빌드에서 비교해야 한다. |
| index는 이미 `arguments` 우선, `directory` 기준 working-directory 처리와 상대 source argument 제거를 구현한다. | `faultdebug/index.py` | 필요한 증분 개선은 compdb 발견·입력 검증·부족한 coverage의 표시다. 기존 정상화 코드를 중복하지 않는다. |
| bundle은 source/index/binary hash와 binary Build-ID를 저장한다. | `faultdebug/bundle.py` | 별도 debug ELF의 Build-ID 매칭은 후속 확장이다. 소스 hash를 보유하는 것과 binary에서 함수 이벤트를 수집하는 것은 별도 보장이다. |

## 우선 개선 5개와 acceptance

| 우선순위 | 제안 및 범위 | 근거와 완료 조건 |
| --- | --- | --- |
| P0 | **대상 preflight.** ELF 형식·아키텍처, hook symbol, runtime dependency, Build-ID, debug sections, source/build/compdb 경로를 읽기 전용 JSON으로 보고한다. 비계측 ELF에는 재빌드 필요를 명시한다. | uftrace도 trace 가능한 입력을 구분하고 uprobes도 대상 위치를 요구한다. acceptance: 비계측 baseline을 계측 가능이라고 판정하지 않음; 누락·손상·stripped 입력이 traceback 대신 명확한 상태를 반환; 검사 중 target 실행 또는 파일 변경 없음. [uftrace record](https://github.com/namhyung/uftrace/blob/master/doc/uftrace-record.md), [kernel uprobes](https://docs.kernel.org/trace/uprobetracer.html) |
| P0 | **기존 CMake용 분리 prepare.** 선택 타깃, 원본 source root, 기존 build 정보를 읽고 새 workspace에 include와 명령 계획을 작성한다. compiler·generator·필요한 cache 값을 보존하고 기존 include를 덮어쓰지 않는다. | `CMAKE_PROJECT_INCLUDE`는 3.15+, `DEFER`는 3.19+다. 3.19 미만, 지원하지 않는 generator, 불명확한 toolchain/cache, imported/interface/alias target은 명확히 제한한다. acceptance: 기존 source/build hash 보존; 지정 executable에 hook/runtime 연결; 지정하지 않은 타깃에 전역 flags 전파 없음. [project include](https://cmake.org/cmake/help/latest/variable/CMAKE_PROJECT_INCLUDE.html), [DEFER](https://cmake.org/cmake/help/latest/command/cmake_language.html#deferring-calls), [target link scope](https://cmake.org/cmake/help/latest/command/target_link_libraries.html) |
| P1 | **컴파일 DB 확보와 coverage 진단.** 명시 입력을 우선하고 source/build 후보에서 DB를 발견한다. 없으면 generator별 export/Bear 경로를 계획에 보여준다. 입력 argv를 실행하지 않는다. | Clang 규격의 `directory`, `arguments`, `command` 의미를 유지한다. acceptance: 빈 DB·누락 소스·entry 오류·launcher/response-file 처리 한계를 표시; libclang diagnostics를 PASS로 숨기지 않음; DB가 있다고 전체 소스 coverage를 확정하지 않음. [CMake compile DB](https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html), [Clang 규격](https://clang.llvm.org/docs/JSONCompilationDatabase.html), [Bear](https://github.com/rizsotto/Bear) |
| P1, 후속 | **분리 debug ELF와 binary의 일치 검증.** explicit symbol 경로와 Build-ID를 비교하고 bundle에 원본 경로·hash·매칭 결과를 저장한다. | Sentry Symbolicator와 GDB 경로는 binary/debug identity를 구분한다. acceptance: 다른 빌드의 같은 파일명은 거부; ID 누락은 unresolved; stripped binary+정확한 debug ELF는 일치; 불일치를 경고만 하고 정확한 소스라고 보고하지 않음. [공식 Symbolicator](https://github.com/getsentry/symbolicator/blob/master/docs/advanced/symbol-server-compatibility.md) |
| P1 | **실제 외부 프로젝트 온보딩 검증과 사용 계약.** 작은 실제 프로젝트 2개 이상에서 baseline → preflight → 분리 prepare → build → 정상 실행 → trace artifact를 검증한다. | SDK·tracer·build integration은 각자의 설치/실행 범위가 다르므로 문서 비교로 실행 성공을 대체하지 않는다. acceptance: 외부 pin, compiler, generator, workload oracle, source/build hash 보존, ENTER/EXIT 또는 함수 이벤트 수, drop count를 보고; 런타임 성공과 source resolution 성공을 따로 판정. 공식 target 근거는 아래 고정된 소스 링크다. |

제안한 명령과 판정 필드의 이름은 구현자의 검토를 거쳐 확정한다. 아직 존재하지 않는 backend나 symbol 경로를 CLI 사용 예로 제시하지 않는다.

## 실제 외부 프로젝트 검증용 고정 후보

아래 tag는 최신 버전 추천이 아니라 재현 가능한 integration fixture다. 공식 release와 commit metadata를 확인했으며 executable target은 해당 pin의 CMake source에서 확인했다. 이 연구 작업자가 해당 프로젝트를 다운로드·build·run한 것은 아니다.

| 후보 | 공식 저장소와 고정 commit | 실행 타깃과 필요한 옵션 | 검증 시 주의점 |
| --- | --- | --- | --- |
| cJSON v1.7.18 | [DaveGamble/cJSON](https://github.com/DaveGamble/cJSON), [`acc76239bee01d8e9c858ae2cab296704e52d916`](https://github.com/DaveGamble/cJSON/commit/acc76239bee01d8e9c858ae2cab296704e52d916), [release](https://github.com/DaveGamble/cJSON/releases/tag/v1.7.18) | `cJSON_test`, `ENABLE_CJSON_TEST=ON` (기본). [고정 CMake source](https://github.com/DaveGamble/cJSON/blob/acc76239bee01d8e9c858ae2cab296704e52d916/CMakeLists.txt) | 실행 파일은 `test.c`를 사용하고 cJSON library를 링크한다. 실행 파일만 계측한 경우 library 내부 함수 coverage를 전체 프로젝트 coverage라고 부르지 않는다. |
| zlib v1.3.1 | [madler/zlib](https://github.com/madler/zlib), [`51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf`](https://github.com/madler/zlib/commit/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf), [release](https://github.com/madler/zlib/releases/tag/v1.3.1) | `example`, 대안 `minigzip`; `ZLIB_BUILD_EXAMPLES=ON` (기본). [고정 CMake source](https://github.com/madler/zlib/blob/51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf/CMakeLists.txt) | upstream CMake는 out-of-source configure에서 source `zconf.h`를 `zconf.h.included`로 rename할 수 있다. staging copy를 사용하고 upstream configure의 자체 변경과 FaultDebug 준비 단계의 변경을 구분한다. |

권장 검증 순서:

1. 공식 source pin과 pristine hash 목록을 보관하고 staging source를 만든다.
2. baseline build·정상 workload 결과를 확인한다.
3. preflight에서 baseline을 비계측 또는 재빌드 필요로 판정하는지 확인한다.
4. `prepare`가 기존 source/build를 변경하지 않고 별도 계획·include를 만드는지 확인한다.
5. 분리 build를 실행하고 선택한 executable을 검사한다.
6. 동일 workload의 정상 결과 및 non-empty trace artifact, 이벤트 종류와 drop count를 확인한다.
7. index/source resolution을 별도 검사하고 실패/미실행을 명시한다.

전체 타깃을 자동 계측하지 않은 경우 성공 의미는 **선택 타깃 온보딩 및 관측 성공**이다. 의존 library까지 완전한 함수 coverage, 모든 native crash의 포착, 운영 환경 성능 한계 충족을 포함하지 않는다.

## 후속 조사 및 현재 제한

- uprobe/eBPF 또는 uftrace 결과를 외부 evidence로 수집하는 opt-in adapter는 후속 설계다. 새 이벤트 format, 식별 규칙, 권한과 손실 측정이 필요하다. 현재 기능으로 표현하지 않는다.
- Binary의 hook symbol이나 runtime dependency 존재는 필요한 정적 단서다. 모든 함수의 계측 여부, runtime 초기화 성공, 이벤트 완전성을 증명하지 못한다. 실제 handshake와 trace artifact 검증이 뒤따라야 한다.
- CMake cache를 읽는 것만으로 모든 presets, toolchain 파일, package-manager 상태, 외부 source generated artifact를 복제할 수 있다고 보장하지 않는다. 재현하지 못한 설정은 unresolved로 남기거나 explicit configure option을 요구한다.
- 비교한 도구들의 설치·벤치마크·provider 동작 검증: NOT RUN. codebase-memory graph/index coverage: NOT RUN. 외부 source pin/target 문서 확인: 완료. 실제 외부 프로젝트 실행 결과: 별도 검증 보고서에 기록.

공식 Sentry 문서 사이트의 일부 native 페이지는 조사 도구에서 `text/markdown` content type을 읽지 못했다. 해당 사실을 지원 근거로 사용하지 않았으며, 성공적으로 읽은 Sentry Native 및 Symbolicator의 공식 저장소 문서로 대체했다.
