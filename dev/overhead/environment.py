#!/usr/bin/env python3
"""Record non-secret host controls at a labelled time; never alter host settings."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert not args.output.exists()
    commands = {
        'macos': ['sw_vers'],
        'hardware': ['sysctl', 'hw.model', 'hw.ncpu', 'hw.memsize', 'machdep.cpu.brand_string'],
        'power': ['pmset', '-g', 'batt'],
        'thermal': ['pmset', '-g', 'therm'],
        'docker': ['docker', 'info', '--format', '{{.OSType}} {{.Architecture}} {{.NCPU}} {{.MemTotal}} {{.ServerVersion}}'],
        'disk': ['df', '-h', str(Path(__file__).resolve().parents[2])],
    }
    result = dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(), scope='point-in-time only', checks={})
    for label, command in commands.items():
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        result['checks'][label] = dict(command=command, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
