#!/usr/bin/env python3
"""data/glosses.json の不足語を ECDICT（中国語, MIT）と EJDict（日本語, CC0）で補う。
既存の項目は変更しない。サイトで表示される英単語（bank.json / passages.json）だけを追加する。

使い方:
  python3 tools/build_glosses.py <ecdict.csv> <EJDict/src ディレクトリ>
  ECDICT: https://github.com/skywind3000/ECDICT   EJDict: https://github.com/kujirahand/EJDict
"""
import csv, json, re, sys, os, glob, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ECP, EJP = sys.argv[1], sys.argv[2]
D = lambda f: os.path.join(ROOT, 'data', f)
bank = json.load(open(D('bank.json'), encoding='utf-8'))
pas = json.load(open(D('passages.json'), encoding='utf-8'))
GL = json.load(open(D('glosses.json'), encoding='utf-8'))
ORIG = set(GL)

# ---- サイトで wz() を通る英文 ----
texts = []
for q in bank:
    texts += [q.get('context') or '', q.get('sentence') or '', q.get('stem') or '', q.get('explanation_zh') or '']
    texts += [v or '' for v in q['choices'].values()]
for p in pas.values():
    texts.append(p['part2_text']); texts += list(p['part1_paragraphs'].values())
# index.html と同じ規則（数字に続く th/s などは数字の一部として除外）
WRE = re.compile(r"\d[\d,.]*(?:st|nd|rd|th|s)?\b|[A-Za-z][A-Za-z'’\-]*[A-Za-z]|[A-Za-z]")
toks = collections.Counter(t for t in WRE.findall('\n'.join(texts)) if not t[0].isdigit())

# ---- 辞書 ----
csv.field_size_limit(1 << 30)
EC = {}
with open(ECP, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        w = r['word']; lw = w.lower()
        if lw in EC and EC[lw]['word'] == lw and w != lw: continue  # 小文字の見出しを優先
        if lw not in EC or w == lw: EC[lw] = r
EJ = {}; EJc = {}  # 小文字の見出し（be）を大文字の見出し（Be=ベリリウム）より優先。同じ見出しの複数項目はまとめる
for fn in sorted(glob.glob(os.path.join(EJP, '*.txt'))):
    for line in open(fn, encoding='utf-8'):
        if '\t' not in line: continue
        ws, m = line.rstrip('\n').split('\t', 1)
        for w in ws.split(','):
            w = w.strip()
            if not w: continue
            (EJ if w == w.lower() else EJc).setdefault(w.lower(), []).append(m)
for k, v in EJc.items(): EJ.setdefault(k, v)

POSMAP = {'n': 'n', 'v': 'v', 'vt': 'vt', 'vi': 'vi', 'a': 'adj', 'adj': 'adj', 'ad': 'adv', 'adv': 'adv', 'prep': 'prep',
          'conj': 'conj', 'pl': 'n-pl', 'pron': 'pron', 'art': 'art', 'num': 'num', 'int': 'int', 'interj': 'int', 'abbr': 'abbr', 'aux': 'aux', 'pref': 'prefix', 'suf': 'suffix'}
def zh_of(w):
    r = EC.get(w)
    if not r or not r['translation']: return '', ''
    lines = [l.strip() for l in r['translation'].replace('\\r', '').replace('\\n', '\n').split('\n') if l.strip() and not l.startswith('[')]
    clean = [l for l in lines if not re.search(r'\[[计化医经法电]\]', l)]
    lines = clean or [re.sub(r'\[[^\]]*\]\s*', '', l) for l in lines]
    if not lines: return '', ''
    out = []
    for l in lines[:2]:
        segs = re.split(r'[；;]', l)
        out.append('；'.join(s.strip() for s in segs[:3] if s.strip()))
    z = ' / '.join(out)
    if len(z) > 90: z = z[:88] + '…'
    m = re.match(r'([a-z]+)\.', lines[0])
    return z, POSMAP.get(m.group(1), '') if m else ''
def ja_clean(m):
    m = re.sub(r'《[^》]*》', '', m); m = re.sub(r'〈[^〉]*〉', '', m); m = m.replace('『', '').replace('』', '')
    parts = [p.strip(' ・') for p in re.split(r' / |・', m) if p.strip(' ・')]
    out = ''
    for p in parts[:3]:
        if out and len(out) + len(p) > 110: break
        out = (out + ' / ' if out else '') + p
    return out[:120]
def ja_of(w):
    if w not in EJ: return ''
    ents = [[p for p in re.split(r' / ', m) if p.strip()] for m in EJ[w]]
    if len(ents) == 1: return ja_clean(EJ[w][0])
    rr = [p for i in range(3) for e in ents if i < len(e) for p in [e[i]]]  # 複数項目は順番に
    return ja_clean(' / '.join(rr))
def ej_raw(w): return ' / '.join(EJ.get(w, []))

INFL = re.compile(r'的(过去式|过去分词|现在分词|复数|第三人称单数|比较级|最高级|变形)|（[a-z\-]+的(过去|复数|现在分词)')
JINFL = re.compile(r'の(過去|過去分詞|複数|現在分詞|比較級|最上級|三人称|-ing形)')
CODE = {'p': ('v-ed', '过去式'), 'd': ('v-ed', '过去分词'), 'i': ('v-ing', '现在分词'), '3': ('v-3s', '第三人称单数'),
        's': ('n-pl', '复数'), 'r': ('adj-er', '比较级'), 't': ('adj-est', '最高级')}
# 辞書データの誤りを避けるための少数の手動補正
LEMMA_FIX = {'was': ('be', 'p'), 'were': ('be', 'p'), 'are': ('be', '3'), 'am': ('be', '3'), 'does': ('do', '3'), 'acts': ('act', 's')}
NO_LEMMA = {'charles', 'cummins', 'newlands', 'its', 'his', 'this', 'us', 'thus'}  # 人名・代名詞を複数形と誤認しない
ENTRY_FIX = {
    'a': {'zh': 'art. 一个；某一；每一', 'ja': '一つの,ある / …につき,…ごとに', 'pos': 'art'},
    'an': {'zh': 'art. 一个；某一；每一（用于元音前）', 'ja': '(母音の前で)一つの,ある / …につき', 'pos': 'art'},
    'x': {'zh': 'n. 字母X；未知数；X（指代某事物）', 'ja': '英語アルファベットの第24字 / 未知数 / (未知の)X', 'pos': 'n'},
    'well': {'zh': 'adv. 好；充分地；很 / a. 健康的 / n. 井', 'ja': 'よく,上手に / 十分に,かなり / 健康で / 井戸', 'pos': 'adv'},
}
def base_of(w):
    if w in NO_LEMMA: return None, None
    if w in LEMMA_FIX: return LEMMA_FIX[w]
    r = EC.get(w)
    if r and r['exchange']:
        ex = dict(x.split(':', 1) for x in r['exchange'].split('/') if ':' in x)
        b = ex.get('0'); c = ex.get('1', '')
        b = (b or '').lower(); br = EC.get(b)
        # 原形側の exchange にもこの語があるときだけ採用（was→wa, its→it の誤りを防ぐ）
        if b and b != w and br and w in [x.split(':', 1)[1].lower() for x in br['exchange'].split('/') if ':' in x]:
            return b, (c[:1] if c else 'p')
    if r and (r['translation'] or w in EJ): return None, None  # 辞書に独立した見出しがある語は推測しない
    if w in EJ: return None, None
    # 規則変化を推測
    rules = [(r'ies$', 'y', 's'), (r'ied$', 'y', 'p'), (r'([^aeiou])\1ed$', r'\1', 'p'), (r'([^aeiou])\1ing$', r'\1', 'i'),
             (r'ing$', 'e', 'i'), (r'ing$', '', 'i'), (r'ed$', 'e', 'p'), (r'ed$', '', 'p'), (r'es$', '', 's'), (r's$', '', 's'),
             (r'ier$', 'y', 'r'), (r'iest$', 'y', 't'), (r'er$', '', 'r'), (r'est$', '', 't')]
    for pat, rep, code in rules:
        if re.search(pat, w):
            b = re.sub(pat, rep, w)
            if len(b) >= 2 and (b in EC or b in EJ) and (zh_of(b)[0] or ja_of(b)):
                return b, code
    return None, None

def make(w):
    """w（小文字）の項目を作る。作れなければ None"""
    if w in ENTRY_FIX: return dict(ENTRY_FIX[w])
    b, code = base_of(w)
    zh, pos = zh_of(w); ja = ja_of(w)
    if b:
        rz = EC.get(w, {}).get('translation', '') if EC.get(w) else ''
        if w in LEMMA_FIX and w != 'acts' and zh: return {'zh': '【' + b + ' 的变形】' + zh, 'ja': ja or (GL.get(b) or {}).get('ja', '') or ja_of(b), 'pos': 'v', 'lemma': b}
        own = w != 'acts' and bool(zh) and not INFL.search(rz) and bool(ja) and not JINFL.search(ej_raw(w))
        own_zh = own_ja = own  # 両方に独自の意味があるときだけ（including, united など）。それ以外は原形の意味
        ipos, lbl = CODE.get(code, ('v-ed', '变形'))
        bg = GL.get(b)
        bzh = bg['zh'] if bg else zh_of(b)[0]
        bja = bg['ja'] if bg else ja_of(b)
        e = {'zh': zh if own_zh else ('【' + b + ' 的' + lbl + '】' + bzh if bzh else ''),
             'ja': ja if own_ja else bja, 'pos': ipos, 'lemma': b}
        if e['zh'] or e['ja']: return e
    if zh or ja:
        return {'zh': zh, 'ja': ja, 'pos': pos}
    return None

def cands(t):  # index.html の lookup と同じ順
    l = t.lower().replace('’', "'").replace('‘', "'")
    return [l, re.sub(r"'s$", '', l), re.sub(r"'$", '', l), l.strip("'")]
def hit(t): return next((c for c in cands(t) if c in GL), None)

added = 0; nodata = collections.Counter()
def ensure(t, n):
    global added
    if hit(t): return True
    for c in dict.fromkeys(reversed(cands(t))):  # 's を外した形を優先
        if not c or c == "'": continue
        e = make(c)
        if e: GL[c] = e; added += 1; return True
    return False
for t, n in toks.items():
    if ensure(t, n): continue
    if '-' in t:  # 辞書にないハイフン語は分割（サイトも同じ）
        for p in t.split('-'):
            if p and not ensure(p, n): nodata[p.lower()] += n
    else:
        nodata[cands(t)[1]] += n
# 新しい項目だけキー順で追加（既存の順序と内容はそのまま）
out = {k: GL[k] for k in GL if k in ORIG}
for k in sorted(set(GL) - ORIG): out[k] = GL[k]
json.dump(out, open(D('glosses.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('tokens', sum(toks.values()), 'unique forms', len(toks), 'entries before', len(ORIG), 'added', added, 'after', len(out))
print('nodata unique', len(nodata), 'occurrences', sum(nodata.values()))
print('nodata sample', [w for w, _ in nodata.most_common(60)])
