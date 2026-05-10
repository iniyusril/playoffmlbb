import re
from pprint import pprint

with open('liquipedia_text.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# replicate parse_standings preprocessing
start = text.find("Regular Season[edit]")
if start != -1:
    start += len("Regular Season[edit]")
else:
    start = text.find("# Team")
    if start == -1:
        start = 0

end = len(text)
for marker in ("Tiebreakers:", "Show Individual", "Detailed Results"):
    pos = text.find(marker, start)
    if pos != -1 and pos < end:
        end = pos

section = text[start:end]
section = re.sub(r'^\s*[▲▼]\s*\d+\s*$', '', section, flags=re.MULTILINE)
section = re.sub(r'[▲▼]\s*\d+', '', section)
section = re.sub(r"\n\s*(\d+-\d+\s+\d+-\d+\s+[+-]?\d+)", r" \1", section)

# show a window around 'Alter Ego'
idx = section.find('Alter Ego')
print('=== SNIPPET AROUND "Alter Ego" ===')
print(section[idx-120:idx+200])

# show all lines that match the standings pattern
pattern = re.compile(r"\d+\.\s+(.+?)\s+(\d+)-(\d+)\s+(\d+)-(\d+)\s+([+-]?\d+)", re.MULTILINE)
print('\n=== MATCHES (team -> groups) ===')
for m in pattern.finditer(section):
    print('MATCH:', m.group(0))
    print(' name:', repr(m.group(1)))
    print(' w-l:', m.group(2), m.group(3), ' gw-gl:', m.group(4), m.group(5), ' diff:', m.group(6))

# print whether Alter Ego was matched by regex
m = pattern.search(section)
print('\nFirst match start at', m.start() if m else None)

# also print lines of section for manual inspection
lines = section.split('\n')
print('\n=== LINES AROUND STANDINGS ===')
for i,ln in enumerate(lines[:40]):
    print(i, repr(ln))
