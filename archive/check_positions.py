import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results.csv')
lines = open(_CSV, encoding='utf-8').readlines()[1:]
vals = set()
for l in lines:
    parts = l.strip().split(',')
    if len(parts) >= 5:
        vals.add(parts[4])
print("row count:", len(lines))
print("sample position values:", sorted(vals)[:30])