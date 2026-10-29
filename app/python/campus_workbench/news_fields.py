"""Explicit news fact fields with conservative OCR spacing normalization."""
import re
import unicodedata
from datetime import date


def fields(text):
    text=unicodedata.normalize('NFKC',text)
    values={'日期':set(),'地点':set(),'主办单位':set()}
    patterns=(r'(?:(\d{4})[ \t]*年[ \t]*)?(\d{1,2})[ \t]*月[ \t]*(\d{1,2})[ \t]*日',
              r'(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)',
              r'(?:日期|时间)[：: \t]*(\d{4})[ \t]*\.[ \t]*(\d{1,2})[ \t]*\.[ \t]*(\d{1,2})(?!\d)')
    for pattern in patterns:
        for match in re.finditer(pattern,text):
            year=int(match[1]) if match[1] else None;month,day=int(match[2]),int(match[3])
            try:date(year if year is not None else 2000,month,day)
            except ValueError:continue
            values['日期'].add(f'{year if year is not None else ""}/{month}/{day}')
    for key,label in [('地点','地点'),('主办单位','(?:主办单位|主办方|主办)')]:
        values[key].update(m.group(1).strip() for m in re.finditer(label+r'[：:]\s*([^\n，。；]{2,40})',text))
    return values
