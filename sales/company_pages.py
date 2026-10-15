"""Select original company news separately from evergreen site sections."""
import re
from datetime import date

MONTHS=('gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre').split()


def preview_date(label):
    # A date printed at the start of a link is a reading hint, not an event fact.
    match=re.match(r'\s*(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\b',label,re.I)
    if not match:return None
    try:return date(int(match[3]),MONTHS.index(match[2].lower())+1,int(match[1]))
    except ValueError:return None


def news_links(options, today=None):
    today=today or date.today();ranked=[]
    for item in options:
        label=item.get('label','');published=preview_date(label)
        if not published:continue
        age=(today-published).days
        if age<0:continue
        # Older delivery announcements remain useful counterevidence. They do
        # not establish that a site is still adequate; read the original page.
        solution=bool(re.search(r'(?:nuov\w*|online|lanciat\w*|rinnovat\w*).{0,65}(?:sito\s+(?:web|internet)|e.?commerce|portale)|(?:sito\s+web|e.?commerce|portale).{0,65}(?:online|lanciat\w*|rinnovat\w*)',label,re.I))
        event=bool(re.search(r'nuov[oaie]\s+(?:marchio|brand|divisione|linea|linee|servizio|mercat\w*)|internazional\w*|espansion\w*|ester[oi]|europe[oa]|distributor\w*',label,re.I))
        if solution and age<=730:ranked.append((0,-published.toordinal(),item['url']))
        elif event and age<=180:ranked.append((1,-published.toordinal(),item['url']))
    return list(dict.fromkeys(url for _,_,url in sorted(ranked)))[:4]
