"""Shared read-only CLI/MCP projections of bounded service evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from .service_report import build_service_report

ServiceSection = Literal['summary', 'services', 'calls', 'causes', 'events',
                         'native_relations', 'unresolved', 'evidence_files']
COLLECTIONS = ('services', 'calls', 'causes', 'events', 'native_relations',
               'unresolved', 'evidence_files')
MAX_PAGE_SIZE = 200
MAX_RESPONSE_BYTES = 1024 * 1024
QUERY_CONTRACT = 'service-query-v1'


def query_service_flow(evidence: Path, *, section: ServiceSection = 'summary',
                       page: int = 0, page_size: int = 100,
                       snapshot_id: str | None = None) -> dict:
    """Revalidate frozen inputs on every call; reject stale pagination explicitly.

    This is a content fingerprint, not an atomic live-filesystem snapshot or a
    cache. No source bundle enrichment is performed by this query contract.
    """
    if section not in ('summary', *COLLECTIONS):
        raise ValueError('Unknown service-flow section')
    if isinstance(page, bool) or not isinstance(page, int) or page < 0:
        raise ValueError('Service-flow page must be a nonnegative integer')
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f'Service-flow page size must be 1..{MAX_PAGE_SIZE}')
    if snapshot_id is not None and (not isinstance(snapshot_id, str) or len(snapshot_id) != 64
                                   or any(c not in '0123456789abcdef' for c in snapshot_id)):
        raise ValueError('Invalid service-flow snapshot ID')
    if section == 'summary' and page != 0:
        raise ValueError('Service-flow summary has only page zero')
    model = build_service_report(Path(evidence))
    manifest = sorted(model['evidence_files'], key=lambda row: row['path'])
    fingerprint = hashlib.sha256(json.dumps(
        {'contract': QUERY_CONTRACT, 'files': manifest}, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    if snapshot_id is not None and snapshot_id != fingerprint:
        raise ValueError('Service-flow evidence changed; restart at page zero with a new snapshot ID')
    result = {'schema': 1, 'snapshot_id': fingerprint, 'session_id': model['session_id'],
              'section': section, 'counts': {name: len(model[name]) for name in COLLECTIONS},
              'limitations': model['limitations']}
    if section != 'summary':
        rows = model[section]
        start = page * page_size
        items = rows[start:start + page_size]
        result.update(page=page, page_size=page_size, total=len(rows), returned=len(items),
                      next_page=page + 1 if start + len(items) < len(rows) else None, items=items)
    encoded = json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2).encode()
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ValueError('Service-flow response byte budget exceeded; request a smaller page')
    return result
