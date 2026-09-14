#!/usr/bin/env python3
"""Independent, standard-library-only audit of a completed construction profile.

Reads archived facts; never imports the runner, starts a process, or changes raw
artifacts. --write creates two new review files exclusively after all checks.
"""
import argparse
import datetime as dt
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ITERATIONS = 1_500_000_000
BASES = {
    'opentenbase-pg18-pgvector:timing-v1-test-arm64': 'sha256:583632f8a2ba73f694ffed52fcd8e9a9a385da94c2602bfd65de1086a92148c6',
    'opentenbase-pg18-pgvector:timing-v1-arm64': 'sha256:af1ee2f012f452048c080b591c5456e8a5a83fea77fb4df6e53f4d28ba395fc7',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + ': expected integer')
    return value


def finite(value, label):
    require(type(value) in (float, int) and math.isfinite(value), label + ': nonfinite/non-number')
    return value


def strict_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON: ' + value)
    def decimal(value):
        return finite(float(value), 'JSON decimal')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=decimal)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value):
    result = dt.datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'timestamp missing timezone')
    return result


@lru_cache(maxsize=4)
def checksum(iterations=ITERATIONS):
    """Independent integer arrays and periodic visit expansion, no distance loop."""
    integer(iterations, 'iterations', 1)
    require(iterations <= 4_000_000_000, 'iterations exceed reviewed C range')
    distances = []
    for index in range(1024):
        left = [(11 * index + 7 * dimension + index // 13) % 17 - 8 for dimension in range(32)]
        right = [(3 * index + 5 * dimension + index // 7) % 19 - 9 for dimension in range(32)]
        distances.append(sum((a - b) ** 2 for a, b in zip(left, right)))
    full_periods, remainder = divmod(iterations, 1024)
    return full_periods * sum(distances) + sum(distances[(17 * i) % 1024] for i in range(remainder))


def resource_fields(text):
    sections = re.split(r'^FILE:([^\n]+)\n', text, flags=re.M)
    require(sections[0] == '' and len(sections) % 2 == 1, 'resource sections malformed')
    fields = {}
    for name, value in zip(sections[1::2], sections[2::2]):
        require(name not in fields, 'duplicate resource section')
        fields[name] = value.strip()
    require(set(fields) == {'cpu.stat', 'cpu.max', 'cpuset.cpus.effective', 'memory.current',
                            'memory.events', 'io.stat', 'cpu.pressure'}, 'missing resource sections')
    require(fields['cpuset.cpus.effective'] == '0-9', 'guest affinity changed')
    require(fields['cpu.max'] == 'max 100000', 'guest CPU quota changed')
    require(fields['memory.current'].isdigit() and int(fields['memory.current']) > 0, 'memory record invalid')
    for name in ('cpu.stat', 'memory.events'):
        counters = {}
        for line in fields[name].splitlines():
            key, value = line.split()
            require(key not in counters and value.isdigit(), 'invalid resource counter')
            counters[key] = int(value)
        fields[name] = counters
    require({'usage_usec', 'user_usec', 'system_usec'} <= fields['cpu.stat'].keys(), 'CPU counters missing')
    require({'oom', 'oom_kill'} <= fields['memory.events'].keys(), 'memory events missing')
    require(bool(fields['cpu.pressure']), 'pressure missing: record unavailable explicitly')
    return fields


def audit_record(record, kind, number):
    require(record['kind'] == kind and integer(record['number'], 'number', 1) == number, 'probe identity/order changed')
    require(record['status'] == 'verified' and 'error' not in record, 'probe failed')
    require(integer(record['iterations_per_process'], 'record iterations', 1) == ITERATIONS, 'work changed')
    require(timestamp(record['started_at_utc']) < timestamp(record['finished_at_utc']), 'probe timestamps reversed')
    for side in ('before', 'after'):
        require("Now drawing from 'AC Power'" in record['ac_' + side], 'AC not established')
    before_resources = resource_fields(record['resources_before'])
    after_resources = resource_fields(record['resources_after'])
    for name in ('cpu.stat', 'memory.events'):
        require(before_resources[name].keys() == after_resources[name].keys(), 'resource counters changed')
        require(all(after_resources[name][key] >= value for key, value in before_resources[name].items()),
                'resource counter reset')
    clocks = [record['host_clock_before'], record['host_clock_after']]
    for clock in clocks:
        for key in ('realtime_ns', 'monotonic_ns'):
            integer(clock[key], key, 1)
        integer(clock['sampling_span_ns'], 'clock sampling span')
    wall = clocks[1]['realtime_ns'] - clocks[0]['realtime_ns']
    mono = clocks[1]['monotonic_ns'] - clocks[0]['monotonic_ns']
    require(integer(record['host_wall_elapsed_ns'], 'host wall', 1) == wall, 'wall delta mismatch')
    require(integer(record['host_monotonic_elapsed_ns'], 'host mono', 1) == mono, 'mono delta mismatch')
    require(type(record['host_wall_minus_monotonic_ns']) is int and
            record['host_wall_minus_monotonic_ns'] == wall - mono, 'clock drift mismatch')
    require(abs(wall - mono) <= 100_000_000, 'predeclared 100ms clock limit exceeded')
    data = strict_loads(record['raw_stdout'])
    require(data == record['result'], 'raw/result mismatch')
    require(record['raw_stderr'] == '', 'unexpected calculation stderr')
    require(integer(data['schema'], 'schema') == 1 and data['test_only'] is True and data['verified'] is True,
            'data status/schema invalid')
    require(data['scope'] == 'fixed_arithmetic_three_processes', 'calculation scope changed')
    require(integer(data['dimensions'], 'dimensions') == 32 and integer(data['inputs'], 'inputs') == 1024,
            'calculation inputs changed')
    require(data['affinity'] == list(range(10)) and all(type(x) is int for x in data['affinity']), 'affinity invalid')
    require(integer(data['iterations_per_process'], 'iterations', 1) == ITERATIONS, 'iterations changed')
    require(integer(data['expected_checksum'], 'expected checksum', 1) == checksum(), 'integer reference mismatch')
    outer = integer(data['elapsed_ns'], 'outer elapsed', 1)
    processes = data['processes']
    require(len(processes) == 3, 'participant count changed')
    pids, cpu = set(), 0
    for index, process in enumerate(processes):
        require(integer(process['participant'], 'participant') == index and
                process['role'] == ('leader' if index == 0 else 'worker'), 'participant role/order mismatch')
        pid = integer(process['pid'], 'PID', 1)
        require(pid not in pids, 'duplicate PID')
        pids.add(pid)
        require(integer(process['iterations'], 'actual iterations', 1) == ITERATIONS, 'participant work changed')
        require(integer(process['checksum'], 'checksum', 1) == checksum(), 'participant checksum mismatch')
        require(integer(process['elapsed_ns'], 'participant elapsed', 1) <= outer, 'participant exceeds outer wall')
        process_cpu = sum(integer(process[key], key) for key in ('user_cpu_us', 'system_cpu_us'))
        require(process_cpu > 0, 'participant did no measured CPU work')
        cpu += process_cpu
        for key in ('minor_faults', 'major_faults', 'voluntary_switches', 'involuntary_switches'):
            integer(process[key], key)
    return {'outer_wall_s': outer / 1e9, 'sum_process_cpu_s': cpu / 1e6,
            'host_exec_monotonic_s': mono / 1e9, 'host_minus_guest_s': (mono - outer) / 1e9,
            'host_wall_minus_monotonic_ns': wall - mono,
            'resource_cpu_usage_delta_us': after_resources['cpu.stat']['usage_usec'] - before_resources['cpu.stat']['usage_usec']}


def describe(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return {'values': values, 'min': min(values), 'median': statistics.median(values), 'max': max(values),
            'max_over_min': max(values) / min(values), 'sample_cv': math.sqrt(variance) / mean}


def audit_records(summary):
    require(summary['schema'] == 2 and summary['test_only'] is True and summary['profile'] == 'construction', 'wrong profile')
    require(summary['status'] == 'completed' and 'error' not in summary, 'not a completed batch')
    require(len(summary['records']) == 12 and len(summary['warmups']) == 1 and 'sizing' not in summary,
            'fixed 12 formal + 1 warmup violated')
    ordered = summary['warmups'] + summary['records']
    require(summary['attempts'] == ordered, 'attempts omitted/reordered/replaced')
    expected = [('warmup', 1)] + [('formal', number) for number in range(1, 13)]
    values = [audit_record(record, kind, number) for record, (kind, number) in zip(ordered, expected)]
    for before, after in zip(ordered, ordered[1:]):
        require(timestamp(before['finished_at_utc']) <= timestamp(after['started_at_utc']), 'overlapping/reordered probes')
        require(before['host_clock_after']['monotonic_ns'] < after['host_clock_before']['monotonic_ns'], 'monotonic order changed')
    descriptive = {name: describe([value[name] for value in values[1:]])
                   for name in ('outer_wall_s', 'sum_process_cpu_s')}
    for name, fields in descriptive.items():
        require(summary['descriptive'][name]['values'] == fields['values'], 'formal values/warmup exclusion mismatch')
        for field in ('min', 'median', 'max', 'max_over_min', 'sample_cv'):
            require(math.isclose(finite(summary['descriptive'][name][field], field), fields[field], rel_tol=1e-12, abs_tol=1e-12),
                    'description mismatch: ' + name + '/' + field)
    return descriptive, values


def disassembly_evidence(text):
    matches = list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:\s*$', text, re.M))
    bodies = {match.group(2): text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
              for index, match in enumerate(matches)}
    require('calculate' in bodies and 'distance32' in bodies, 'expected binary functions missing')
    calls = re.findall(r'^\s*([0-9a-f]+):.*\bbl\s+[0-9a-f]+ <distance32>', bodies['calculate'], re.M)
    backs = re.findall(r'^\s*([0-9a-f]+):.*\bb\.ne\s+([0-9a-f]+) <calculate\+[^>]+>', bodies['calculate'], re.M)
    loop = [(call, source, target) for call in calls for source, target in backs
            if int(target, 16) <= int(call, 16) < int(source, 16)]
    require(loop, 'distance call not verified inside backward calculation loop')
    require(re.search(r'\bv\d+\.', bodies['distance32']) is not None, 'SIMD distance instructions missing')
    return {'distance_call_loop_addresses': loop, 'distance_function_has_simd': True,
            'interpretation': 'actual loop calls retained; vectorization allowed; not a hardware-frequency measurement'}


def audit_run(directory):
    root = Path(directory).resolve()
    bound = {}
    def read(name):
        path = root / name
        bound[name] = digest(path)
        return strict_loads(path.read_text())
    summary = read('summary.json')
    protocol, initial = read('protocol.json'), read('initial-protocol.json')
    require(summary['protocol_sha256'] == bound['protocol.json'], 'protocol hash mismatch')
    require(all(protocol[key] == value for key, value in initial.items()), 'frozen protocol changed initial fields')
    expected = {'schema': 2, 'test_only': True, 'profile': 'construction', 'sizing_probes': 0,
                'sizing_iterations_per_process': None, 'warmup_probes': 1, 'formal_probes': 12,
                'iterations_per_process': ITERATIONS, 'expected_checksum_per_process': checksum(),
                'participants': 3, 'dimensions': 32, 'input_vectors': 1024,
                'warmup_used_for_selection_or_statistics': False, 'budget_including_build_s': 300,
                'probe_timeout_s': 30, 'container_sleep_s': 300, 'cleanup_outside_budget': True,
                'max_host_realtime_monotonic_difference_ns': 100_000_000,
                'schedule': list(range(1, 13)), 'stop_on_failure': True, 'replacement_or_extra_probes': False,
                'network': 'none', 'database': 'none', 'memory_bytes': 536870912,
                'linux_guest_cpu_affinity': list(range(10)), 'bases': BASES}
    for key, value in expected.items():
        require(protocol[key] == value and type(protocol[key]) is type(value), 'protocol mismatch: ' + key)
    sources = {path.name: digest(path) for path in (root / 'source').iterdir()}
    require(set(sources) == {'run.py', 'calibrate.c', 'compile.sh', 'Dockerfile', 'method.md'}, 'source archive incomplete')
    require(summary['source_hashes_unchanged'] is True and
            summary['input_hashes_at_finish'] == summary['sources'] == protocol['sources'] == sources, 'source hash mismatch')
    bound.update({'source/' + name: value for name, value in sources.items()})
    binary = read('binary-hashes.json')
    require(binary == summary['binary_hashes'], 'binary hash manifests differ')
    require(binary == {path.name: digest(path) for path in (root / 'binary').iterdir()}, 'binary archive changed')
    require({'calibrate', 'calibrate.c', 'disassembly.txt', 'compiler-identity.txt', 'vectorization.txt', 'ldd.txt'} == set(binary),
            'binary/compiler evidence missing')
    require(protocol['binary_sha256'] == binary['calibrate'] and binary['calibrate.c'] == sources['calibrate.c'], 'binary/source binding mismatch')
    bound.update({'binary/' + name: value for name, value in binary.items()})
    compiler = (root / 'binary/compiler-identity.txt').read_text()
    require(binary['calibrate'] in compiler and sources['calibrate.c'] in compiler and 'gcc -O2' in compiler,
            'compiler manifest does not bind source/binary')
    optimization = disassembly_evidence((root / 'binary/disassembly.txt').read_text())
    require('vectorized' in (root / 'binary/vectorization.txt').read_text(), 'vectorization report missing')
    descriptive, values = audit_records(summary)
    require(timestamp(protocol['frozen_at_utc']) < timestamp(summary['warmups'][0]['started_at_utc']), 'protocol froze after probes began')
    probes = summary['attempts']
    expected_names = {f"{record['kind']}-{record['number']:02d}.json" for record in probes}
    require({path.name for pattern in ('formal-*.json', 'warmup-*.json', 'sizing-*.json') for path in root.glob(pattern)} == expected_names,
            'extra or missing probe file')
    for record in probes:
        require(read(f"{record['kind']}-{record['number']:02d}.json") == record, 'probe/summary mismatch')
    identity, recovered = read('container-identity.json'), read('cleanup-recovered-identity.json')
    scope, cleanup = read('cleanup-scope.json'), read('cleanup.json')
    nonce = summary['nonce']
    require(re.fullmatch('[0-9a-f]{12}', nonce), 'nonce invalid')
    cid = identity['Id']
    require(re.fullmatch('[0-9a-f]{64}', cid), 'container ID invalid')
    for item in (identity, recovered):
        require(item['Id'] == cid and item['Name'] == '/cpu-calibration-' + nonce and item['Image'] == protocol['image_id'] and
                item['Config']['Labels']['cpu.calibration.nonce'] == nonce, 'ownership mismatch')
    require(scope == {'container_name': 'cpu-calibration-' + nonce, 'nonce': nonce, 'image_id': protocol['image_id']}, 'cleanup scope mismatch')
    require(identity['Mounts'] == recovered['Mounts'] == cleanup['removed_owned_volumes'], 'mount identity changed')
    require(cleanup == summary['cleanup'] and cleanup['status'] == 'verified' and cleanup['container_id'] == cid and cleanup['nonce'] == nonce,
            'cleanup not verified')
    config, host = identity['Config'], identity['HostConfig']
    require(config['User'] == 'postgres' and config['Entrypoint'] == ['/bin/sleep'] and config['Cmd'] == ['300'], 'runtime command/user changed')
    for key, value in {'NetworkMode': 'none', 'ReadonlyRootfs': True, 'Memory': 536870912, 'MemorySwap': 536870912,
                       'CpusetCpus': '0-9', 'Privileged': False, 'CapDrop': ['ALL']}.items():
        require(host[key] == value, 'runtime isolation mismatch: ' + key)
    require('no-new-privileges' in host['SecurityOpt'], 'security option missing')
    bases, image = read('base-images.json'), read('built-image.json')
    require(all(bases[tag]['Id'] == value for tag, value in BASES.items()), 'base image changed')
    runtime_layers = bases['opentenbase-pg18-pgvector:timing-v1-arm64']['RootFS']['Layers']
    require(image['Id'] == protocol['image_id'] and image['RootFS']['Layers'][:len(runtime_layers)] == runtime_layers, 'runtime image changed')
    paths = sorted(root.glob('command-*.json'))
    require([path.name for path in paths] == [f'command-{i:03d}.json' for i in range(1, len(paths) + 1)], 'command sequence incomplete')
    commands = [read(path.name) for path in paths]
    executed = [(i, command) for i, command in enumerate(commands)
                if command['argv'] == ['docker', 'exec', cid, '/opt/cpu-calibration/calibrate', str(ITERATIONS)]]
    require(len(executed) == 13, 'fixed number of calculation commands violated')
    for (index, command), record in zip(executed, probes):
        require(command['returncode'] == 0 and command['stdout'] == record['raw_stdout'] and command['stderr'] == record['raw_stderr'], 'calculation command/raw mismatch')
        require(timestamp(record['started_at_utc']) <= timestamp(command['started_at_utc']) < timestamp(command['finished_at_utc']) <= timestamp(record['finished_at_utc']), 'command timing outside probe')
        require(0 < finite(command['host_elapsed_s'], 'command elapsed') <= record['host_monotonic_elapsed_ns'] / 1e9, 'command elapsed outside host clock scope')
        for offset, field in [(-2, 'ac_before'), (-1, 'resources_before'), (1, 'resources_after'), (2, 'ac_after')]:
            evidence = commands[index + offset]
            require(evidence['returncode'] == 0 and evidence['stdout'] == record[field], 'AC/resource command mismatch')
    def command_match(argv):
        matches = [command for command in commands if command['argv'] == argv]
        require(len(matches) == 1, 'expected exactly one command: ' + str(argv))
        return matches[0]
    removal = command_match(['docker', 'rm', '-f', '-v', cid])
    require(removal['returncode'] == 0, 'owned removal failed')
    absent = [command for command in commands if command['argv'] == ['docker', 'inspect', cid] and command['returncode'] != 0]
    require(len(absent) == 1 and 'no such object' in absent[0]['stderr'].lower() and
            timestamp(absent[0]['started_at_utc']) >= timestamp(removal['finished_at_utc']), 'container absence not verified after removal')
    allowed_nonzero = [absent[0]]
    for mount in identity['Mounts']:
        require(mount['Type'] == 'volume' and re.fullmatch('[0-9a-f]{64}', mount['Name']), 'unexpected owned mount')
        result = command_match(['docker', 'volume', 'inspect', mount['Name']])
        require(result['returncode'] != 0 and 'no such volume' in result['stderr'].lower() and
                timestamp(result['started_at_utc']) >= timestamp(removal['finished_at_utc']), 'volume absence not verified')
        allowed_nonzero.append(result)
    invalid = read('invalid-input-checks.json')
    require(protocol['invalid_input_checks_sha256'] == bound['invalid-input-checks.json'], 'parser manifest hash mismatch')
    require(invalid['schema'] == 1 and invalid['status'] == 'verified' and
            invalid['scope'] == 'invalid arguments only; no calculation', 'parser manifest invalid')
    parser_commands = [command for command in commands if command['argv'][:4] == ['docker', 'exec', cid, '/opt/cpu-calibration/calibrate'] and command['argv'][-1] != str(ITERATIONS)]
    require([command['argv'][-1] for command in parser_commands] == ['', '-1', '+1', 'abc', '4000000001'], 'unexpected extra calculation/parser command')
    require(all(command['returncode'] == 2 and command['stdout'] == '' for command in parser_commands), 'invalid parser input accepted')
    require(invalid['records'] == [dict(argument=command['argv'][-1], returncode=command['returncode'],
                                      stdout=command['stdout'], stderr=command['stderr']) for command in parser_commands],
            'parser manifest/command mismatch')
    require(all(timestamp(command['finished_at_utc']) < timestamp(protocol['frozen_at_utc']) for command in parser_commands),
            'parser validation after calculation began')
    allowed_nonzero.extend(parser_commands)
    require(all('error' not in command for command in commands), 'unexpected failed command')
    for command in commands:
        require(command['returncode'] == 0 or command in allowed_nonzero, 'unexpected unsuccessful command')
        if command['argv'][:2] == ['docker', 'rm']:
            require(command == removal, 'unexpected removal outside owned scope')
        require(timestamp(command['started_at_utc']) < timestamp(command['finished_at_utc']), 'command timestamps reversed')
        require(finite(command['host_elapsed_s'], 'command duration') > 0, 'command duration invalid')
    discrepancies = [{'kind': record['kind'], 'number': record['number'], 'host_minus_guest_s': value['host_minus_guest_s']}
                     for record, value in zip(probes, values) if value['host_minus_guest_s'] < 0]
    gaps = [value['host_minus_guest_s'] for value in values]
    require(digest(root / 'summary.json') == bound['summary.json'], 'summary changed during audit')
    return {'schema': 1, 'review_status': 'verified', 'test_only': True, 'no_acceptance_claim': True,
            'reviewed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'audit_source_sha256': digest(Path(__file__)), 'summary_sha256': bound['summary.json'],
            'protocol_sha256': bound['protocol.json'], 'method_sha256': sources['method.md'],
            'source_sha256': sources, 'binary_sha256': binary, 'artifact_sha256': bound,
            'formal_probes': 12, 'warmup_probes': 1, 'sizing_probes': 0, 'process_records': 39,
            'iterations_per_process': ITERATIONS, 'independent_expected_checksum': checksum(),
            'descriptive': descriptive, 'ordered_probe_clock_comparison': values,
            'host_minus_guest_s': {'min': min(gaps), 'max': max(gaps), 'guest_exceeds_host': discrepancies},
            'optimization_evidence': optimization, 'cleanup': cleanup,
            'invalid_input_checks': invalid,
            'limits': ['One fixed batch; no stability threshold, window selection, replacement or HNSW acceptance.',
                       'No normalization or reinterpretation of historical HNSW measurements.',
                       'CPU sums process scopes; outer wall includes barrier/reaping; overlapping elapsed is not summed.',
                       'Fixed small-input arithmetic is not HNSW memory, locking or IO work; duration does not prove execution-state control.',
                       'Guest/host clock gap is descriptive; any guest-exceeds-host case requires explicit review, not sample deletion.']}


def report(review):
    wall, cpu = (review['descriptive'][key] for key in ('outer_wall_s', 'sum_process_cpu_s'))
    lines = ['# 构建时长量级固定工作校准：独立审计', '',
             '固定 1 次预热与 12 次正式探测完整，39 条进程记录的工作量、独立整数答案、源码/方法/二进制摘要、命令与清理证据通过核对。',
             '这是一批描述性校准，不建立环境受控或 HNSW 5% 验收，也不筛选窗口或校正历史数据。', '',
             f"每进程固定 {ITERATIONS:,} 次，checksum `{review['independent_expected_checksum']}`；预热不进入下表统计。", '',
             '| 指标 | 最小 / s | 中位 / s | 最大 / s | 最大/最小 | 样本 CV |', '|---|---:|---:|---:|---:|---:|']
    for name, values in [('三进程整体 wall', wall), ('三进程 CPU 合计', cpu)]:
        lines.append(f"| {name} | {values['min']:.6f} | {values['median']:.6f} | {values['max']:.6f} | {values['max_over_min']:.6f} | {values['sample_cv']:.6f} |")
    lines += ['', '| 正式顺序 | Guest outer wall / s | 进程 CPU 合计 / s | Host exec 单调 elapsed / s | Host − guest / s |',
              '|---|---:|---:|---:|---:|']
    for number, value in enumerate(review['ordered_probe_clock_comparison'][1:], 1):
        lines.append(f"| {number} | {value['outer_wall_s']:.9f} | {value['sum_process_cpu_s']:.6f} | {value['host_exec_monotonic_s']:.9f} | {value['host_minus_guest_s']:.9f} |")
    gap = review['host_minus_guest_s']
    lines += ['', f"含预热的 host − guest 差值范围 {gap['min']:.9f}–{gap['max']:.9f} 秒；guest 超过 host 的记录数为 {len(gap['guest_exceeds_host'])}。该差值只用于口径核对，不作性能挑样门槛。", '',
              '反汇编确认实际循环逐次调用距离函数，向量化内循环保留。每进程 CPU 不含输入生成、fork 或整数参考；guest outer wall 包含起跑屏障与回收，host 时钟还包含 docker exec 往返。进程 elapsed 不相加。', '',
              '全部自有容器和匿名卷清理已由归档命令核实；审计没有执行数据库、Docker 或算术负载，没有修改原 summary。', '',
              '原正式性能结果继续保留 9/12 项支持、3 项未证明；没有将本次固定算术耗时归因到硬件频率或产品 C 缺陷。', '',
              '原始证据：[冻结协议](protocol.json)、[完整记录](summary.json)、[独立审计与摘要](independent-review.json)。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    review = audit_run(args.directory)
    if args.write:
        targets = [args.directory / 'independent-review.json', args.directory / 'report.md']
        require(all(not path.exists() for path in targets), 'review outputs already exist; refusing overwrite')
        with targets[0].open('x') as handle:
            json.dump(review, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
        with targets[1].open('x') as handle:
            handle.write(report(review))
    print(json.dumps({key: review[key] for key in ('review_status', 'formal_probes', 'warmup_probes',
                                                   'independent_expected_checksum', 'host_minus_guest_s')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
