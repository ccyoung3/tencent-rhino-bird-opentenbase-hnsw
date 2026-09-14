#!/usr/bin/env python3
"""Functional cross-check of common-build NORMAL images; not performance evidence."""
import json
import tarfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

import acceptance as a
import acceptance_stack as stack
import run


def main():
    output = run.RESULTS_ROOT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-bounded-acceptance-normal')
    output.mkdir()
    build = a.read(a.SNAPSHOT / 'build-manifest.json')
    assert build['status'] == 'passed'
    images = {label: build['images'][('baseline' if label == 'baseline' else 'candidate') + '-normal']['id']
              for label in a.CONDITIONS}
    sources = [Path(__file__), Path(a.__file__), Path(stack.__file__)]
    a.dump(output / 'protocol.json', dict(purpose='functional only, no overhead inference', images=images,
        source_sha256={p.name: a.sha(p) for p in sources}, build_manifest_sha256=a.sha(a.SNAPSHOT / 'build-manifest.json')))
    with tarfile.open(output / 'tooling-at-start.tar.gz', 'x:gz') as archive:
        for path in sources:
            archive.add(path, arcname=path.name)
    result = dict(status='running', checks=[], builds=[])
    print(output, flush=True)
    try:
        with stack.panel(output / 'fixture', images, large_rows=100000, small_rows=30000) as replicas:
            for label, replica in replicas.items():
                watcher = replica.connect(watcher=True)
                assert watcher.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
                try:
                    watcher.execute('SELECT * FROM hnsw_accept.large LIMIT 1')
                    raise AssertionError('observer must not read test payload')
                except Exception as error:
                    assert getattr(error, 'sqlstate', None) == '42501', 'expected schema/table privilege denial'
                watcher.close()
                result['checks'].append(label + ':restricted-observer-role')
                for w, s in a.SCENES:
                    directory = replica.folder / f'w{w}-s{int(s)}'
                    item = a.measure(replica, directory, label, w, s, False, require_ac=False)
                    result['builds'].append({**item, 'source': str(directory.relative_to(output))})
                    table = 'small' if s else 'large'
                    with replica.connect() as conn:
                        assert conn.execute("SELECT indisvalid FROM pg_index WHERE indexrelid='hnsw_accept.items_hnsw'::regclass").fetchone()[0]
                        conn.execute('SET enable_seqscan=off; SET hnsw.ef_search=100')
                        query = conn.execute(f'SELECT embedding::text FROM hnsw_accept.{table} WHERE id=1').fetchone()[0]
                        sql = f'SELECT id, embedding <-> %s::vector AS distance FROM hnsw_accept.{table} ORDER BY embedding <-> %s::vector LIMIT 10'
                        plan = conn.execute('EXPLAIN (FORMAT JSON) ' + sql, (query, query)).fetchone()[0]
                        answer = conn.execute(sql, (query, query)).fetchall()
                        assert 'Index Scan' in json.dumps(plan) and 'items_hnsw' in json.dumps(plan)
                        assert len(answer) == 10 and len({r[0] for r in answer}) == 10
                        assert answer[0] == (1, 0.) and [r[1] for r in answer] == sorted(r[1] for r in answer)
                        a.dump(directory / 'query-check.json', dict(plan=plan, answer=answer, valid=True))
                    result['checks'].append(f'{label}:w{w}:spill={s}:build-timing-observer-index-query')
                    a.dump(output / 'summary.json', result)
                    print(result['checks'][-1], flush=True)
        result['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        result['status'] = 'failed'
        result['error'] = type(error).__name__ + ':' + (getattr(error, 'sqlstate', None) or '')
        result['error_locations'] = [{'file': f.filename.rsplit('/', 1)[-1], 'line': f.lineno}
                                    for f in traceback.extract_tb(error.__traceback__)]
    finally:
        a.dump(output / 'summary.json', result)
    print(result['status'], flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
