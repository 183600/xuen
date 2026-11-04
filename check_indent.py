with open('/home/runner/work/xuen/xuen/xuen/config.py', 'r') as f:
    lines = [line.rstrip('\n') for line in f.readlines()]
prev_indent = None
for i, line in enumerate(lines, start=1):
    indent = len(line) - len(line.lstrip())
    if line.strip() != '' and not line.startswith('#'):
        if prev_indent is not None:
            if indent != prev_indent:
                print(f'Line {i}: unexpected indent (prev {prev_indent}, current {indent})')
        prev_indent = len(line) - len(line.lstrip())
    else:
        if line.strip() != '':
            prev_indent = len(line) - len(line.lstrip())
