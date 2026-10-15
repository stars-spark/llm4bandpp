import sys, bs4, re
s = bs4.BeautifulSoup(open(sys.argv[1], encoding='utf-8', errors='ignore').read(), 'html.parser')
for t in s(['script','style']): t.decompose()
txt = s.get_text('\n')
txt = re.sub(r'\n\s*\n+', '\n', txt)
open(sys.argv[2],'w').write(txt)
