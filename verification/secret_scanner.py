import re
import os

patterns = [
    re.compile(r'(?i)(password|secret|api_key|token|access_key)\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'AIza[0-9A-Za-z-_]{35}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'ghp_[0-9a-zA-Z]{36}')
]

skip_dirs = {'.git', 'node_modules', '.venv', 'venv', 'instance', 'recordings', 'evidence', '.gemini'}
findings = []

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for f in files:
        if f.endswith(('.tar', '.pyc', '.png', '.jpg', '.pt', '.weights', '.onnx', '.log')):
            continue
        p = os.path.join(root, f)
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                for line_no, line in enumerate(fh, 1):
                    for pat in patterns:
                        if pat.search(line):
                            if 'example' in p.lower() or 'test' in p.lower() or 'mock' in p.lower() or 'baseline' in p.lower():
                                continue
                            if 'your_' in line.lower() or '_key_here' in line.lower():
                                continue
                            findings.append((p, line_no))
        except Exception:
            pass

print(f"Total potential secret references outside tests/examples: {len(findings)}")
for path, lno in findings[:10]:
    print(f"  {path}:{lno}")
