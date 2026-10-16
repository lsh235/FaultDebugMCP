# An opt-in bridge for CMAKE_PROJECT_INCLUDE. All mutations are confined to an
# isolated build; top-level deferral sees targets declared in nested directories.
include_guard(GLOBAL)
if(CMAKE_VERSION VERSION_LESS 3.20)
  message(FATAL_ERROR "FaultDebug adoption requires CMake >= 3.20")
endif()

function(_faultdebug_adopt_finalize)
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|AMD64)$")
    message(FATAL_ERROR "FaultDebug adoption currently supports Linux x86_64")
  endif()
  find_package(faultdebug CONFIG REQUIRED PATHS "${FAULTDEBUG_ADOPT_PREFIX}" NO_DEFAULT_PATH)
  # The imported runtime must be visible when generator expressions on a
  # nested executable are evaluated in that executable's declaring directory.
  set_property(TARGET faultdebug::faultdebug_runtime PROPERTY IMPORTED_GLOBAL TRUE)
  get_filename_component(_state_dir "${FAULTDEBUG_ADOPT_STATE}" DIRECTORY)
  get_property(_languages GLOBAL PROPERTY ENABLED_LANGUAGES)
  list(FIND _languages "C" _has_c)
  list(FIND _languages "CXX" _has_cxx)
  if(NOT _has_c EQUAL -1)
    set(_note "${_state_dir}/source-note.c")
  elseif(NOT _has_cxx EQUAL -1)
    set(_note "${_state_dir}/source-note.cpp")
  else()
    message(FATAL_ERROR "FaultDebug adoption requires a C or C++ project")
  endif()
  foreach(_language IN ITEMS C CXX)
    list(FIND _languages "${_language}" _language_position)
    if(NOT _language_position EQUAL -1 AND
       (NOT CMAKE_${_language}_COMPILER_ID STREQUAL "Clang" OR
        NOT CMAKE_${_language}_COMPILER_VERSION VERSION_GREATER_EQUAL 18 OR
        CMAKE_${_language}_COMPILER_VERSION VERSION_GREATER_EQUAL 19))
      message(FATAL_ERROR "FaultDebug adoption requires Clang 18 for ${_language}; select it with --cmake-arg=-DCMAKE_${_language}_COMPILER=/absolute/path")
    endif()
  endforeach()
  if(TARGET faultdebug_adopt_snapshot OR TARGET faultdebug_adopt_finalize)
    message(FATAL_ERROR "The project already owns a reserved faultdebug adoption target")
  endif()
  add_custom_target(faultdebug_adopt_snapshot
    COMMAND "${FAULTDEBUG_ADOPT_PYTHON}" -I -c "${FAULTDEBUG_ADOPT_BOOTSTRAP}"
      snapshot --state "${FAULTDEBUG_ADOPT_STATE}"
    BYPRODUCTS "${_state_dir}/source-note.c" "${_state_dir}/source-note.cpp"
      "${_state_dir}/current-snapshot.json"
    VERBATIM)
  add_custom_target(faultdebug_adopt_finalize
    COMMAND "${FAULTDEBUG_ADOPT_PYTHON}" -I -c "${FAULTDEBUG_ADOPT_BOOTSTRAP}"
      finalize --state "${FAULTDEBUG_ADOPT_STATE}"
    VERBATIM)
  foreach(_target IN LISTS FAULTDEBUG_ADOPT_TARGETS)
    if(NOT TARGET "${_target}")
      message(FATAL_ERROR "FaultDebug adoption: unknown target '${_target}'")
    endif()
    get_target_property(_alias "${_target}" ALIASED_TARGET)
    get_target_property(_imported "${_target}" IMPORTED)
    get_target_property(_type "${_target}" TYPE)
    if(_alias OR _imported OR NOT _type MATCHES "^(EXECUTABLE|STATIC_LIBRARY|SHARED_LIBRARY|MODULE_LIBRARY)$")
      message(FATAL_ERROR "FaultDebug adoption needs an owned executable/library target: ${_target}")
    endif()
    if(_target STREQUAL FAULTDEBUG_ADOPT_MAIN_TARGET AND NOT _type STREQUAL "EXECUTABLE")
      message(FATAL_ERROR "The main adoption target must be an executable")
    endif()
    # Appending the link property supports projects using either the plain or
    # keyword target_link_libraries signature, without changing their policy.
    set_property(TARGET "${_target}" APPEND PROPERTY LINK_LIBRARIES faultdebug::faultdebug_runtime)
    if(_type STREQUAL "STATIC_LIBRARY")
      set_property(TARGET "${_target}" APPEND PROPERTY INTERFACE_LINK_LIBRARIES
        "$<LINK_ONLY:faultdebug::faultdebug_runtime>")
    endif()
    set_property(TARGET "${_target}" APPEND PROPERTY BUILD_RPATH
      "$<TARGET_FILE_DIR:faultdebug::faultdebug_runtime>")
    faultdebug_apply_source_filters("${_target}")
    target_link_options("${_target}" PRIVATE -Wl,--build-id=sha1)
    # Old installed selective helpers set source properties in the calling
    # directory. Copy their computed options to each target's real directory.
    get_target_property(_sources "${_target}" SOURCES)
    get_target_property(_source_dir "${_target}" SOURCE_DIR)
    foreach(_source IN LISTS _sources)
      if(_source MATCHES "^\\$<")
        continue()
      endif()
      if(NOT IS_ABSOLUTE "${_source}")
        set(_source "${_source_dir}/${_source}")
      endif()
      get_source_file_property(_options "${_source}" COMPILE_OPTIONS)
      if(_options AND NOT _options MATCHES "NOTFOUND$")
        set_source_files_properties("${_source}" TARGET_DIRECTORY "${_target}"
          PROPERTIES COMPILE_OPTIONS "${_options}")
      endif()
    endforeach()
    add_dependencies("${_target}" faultdebug_adopt_snapshot)
    add_dependencies(faultdebug_adopt_finalize "${_target}")
    # A linked note changes when any captured source changes. This ensures an
    # incremental build cannot bind an old binary to a newer source snapshot.
    # Static/object libraries receive it in the final executable through their
    # explicitly selected sources; archive ELF notes are verified separately.
    if(_type MATCHES "^(EXECUTABLE|SHARED_LIBRARY|MODULE_LIBRARY)$")
      target_sources("${_target}" PRIVATE "${_note}")
      set_source_files_properties("${_note}" TARGET_DIRECTORY "${_target}"
        PROPERTIES GENERATED TRUE)
    endif()
    file(GENERATE OUTPUT "${_state_dir}/binary-${_target}.txt"
      CONTENT "$<TARGET_FILE:${_target}>\n")
    file(GENERATE OUTPUT "${_state_dir}/type-${_target}.txt" CONTENT "${_type}\n")
  endforeach()
endfunction()

cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL _faultdebug_adopt_finalize)
