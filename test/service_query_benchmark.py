#!/usr/bin/env python3
"""Optional descriptive benchmark; no threshold or native recording claim."""
import json, sys, tempfile, time, resource, statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
import service_report_test as fixtures
from faultdebug.service_query import query_service_flow
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp); fixtures.ServiceEvidenceTests().fixture(root)
 row=json.loads((root/'checkout/events.jsonl').read_text().splitlines()[0]);row['kind']='note'
 line=json.dumps(row)+'\n'
 for i in range(8):
  folder=root/f'log-{i}';folder.mkdir();(folder/'events.jsonl').write_text(line*(12500 if i<7 else 12497))
 durations=[]
 for i in range(5):
  started=time.perf_counter(); result=query_service_flow(root);durations.append(time.perf_counter()-started)
 assert result['counts']['events']==100000,result['counts']
 assert result['counts']['calls']==1,result['counts']
 record={'workload':'synthetic schema-1 application rows, two native FDAR captures; no native recording run',
         'events':100000,'runs':5,'input_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
         'seconds':durations,'median_seconds':statistics.median(durations),
         'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
         'summary_json_bytes':len(json.dumps(result,indent=2).encode()),'counts':result['counts']}
 print(json.dumps(record,indent=2))
