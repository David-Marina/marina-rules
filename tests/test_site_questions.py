"""Question answers are projections of records, including scope/market transitions and structured values."""
import copy
import html
import json
import re
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import marina_rules as mr

from test_site import ROOT, LD_RE, built, manifest, site, text  # shared build fixtures


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def elements(self, tag=None):
        return [c for c in self.children if isinstance(c, Node) and (tag is None or c.tag == tag)]

    def find(self, tag):
        return [c for n in self.elements() for c in ([n] if n.tag == tag else []) + n.find(tag)]

    def plain(self):
        return ''.join(c.plain() if isinstance(c, Node) else c for c in self.children)


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(source)
        assert len(self.stack) == 1

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'meta', 'link', 'br'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        assert self.stack[-1].tag == tag
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def question_pages(manifest):
    return [p for p in manifest['pages'] if p['kind'] == 'question']


def target_records(t, records):
    return [r for r in records if (r.file.split('/')[0], r.scope, r.rule) ==
            (t['prefix'], t['scope'], t['rule']) and t['market'] in r.market.split('+')]


def decode_value(node):
    """Read the value from rendered HTML, independently of the generator's rendering functions."""
    value = node.elements()[0]
    if value.tag == 'code':
        raw = value.plain()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fact-page rendering writes scalar lists without JSON quotes, e.g. session times.
            if raw.startswith('[') and raw.endswith(']'):
                return raw[1:-1].split(', ') if raw[1:-1] else []
            return raw
    if value.tag == 'table':
        rows = value.elements('tr')
        if value.attrs.get('class') == 'kv':
            return {r.elements('th')[0].plain(): decode_value(r.elements('td')[0]) for r in rows}
        keys = [c.plain() for c in rows[0].elements('th')]
        return [dict(zip(keys, (decode_value(c) for c in row.elements('td')))) for row in rows[1:]]
    assert value.tag == 'ol'
    return [decode_value(li) for li in value.elements('li')]


def test_questions_are_safe_titles_and_only_resolving_selectors():
    qs, records = site.questions(), mr.records()
    assert 18 <= len(qs) <= 20
    assert len({q['slug'] for q in qs}) == len(qs)
    for q in qs:
        assert set(q) == {'slug', 'zh', 'en', 'targets'}
        assert re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', q['slug'])
        assert all(not any(c.isdigit() for c in q[lang]) for lang in ('zh', 'en'))
        assert q['targets']
        for t in q['targets']:
            assert set(t) == {'prefix', 'scope', 'rule', 'market'}
            assert t['scope'] in mr.scopes(t['prefix'])
            assert target_records(t, records), (q['slug'], t)
        series = site.question_series(q, records)
        for market, rs in series:
            assert rs[-1].effective_to is None
            assert all(market in r.market.split('+') and not r.contracts for r in rs)
            assert all(a.effective_to == b.effective_from for a, b in zip(rs, rs[1:]))


@pytest.mark.parametrize('change', ['digits_en', 'digits_zh', 'unsafe_slug', 'duplicate', 'invented_value'])
def test_question_input_rejects_unsafe_or_factual_handwritten_content(monkeypatch, change):
    qs = copy.deepcopy(site.questions())
    if change.startswith('digits_'):
        qs[0][change.removeprefix('digits_')] += '２'
    elif change == 'unsafe_slug':
        qs[0]['slug'] = '../outside'
    elif change == 'duplicate':
        qs.append(qs[0])
    else:
        qs[0]['value'] = 'invented'
    monkeypatch.setattr(site, '_read', lambda _: json.dumps(qs))
    with pytest.raises(ValueError):
        site.questions()


def test_broken_overlapping_ended_and_conditional_histories_are_rejected():
    q = next(q for q in site.questions() if q['slug'] == 'chinext-price-limit')
    rs = sorted(target_records(q['targets'][0], mr.records()), key=lambda r: r.effective_from)
    for changed in ([rs[0]], [], [rs[0], rs[0], rs[1]],
                    [replace(rs[0], effective_to=None), rs[1]],
                    [replace(rs[0], contracts={'any': []}), rs[1]]):
        with pytest.raises(ValueError):
            site.question_series(q, changed)
    hk = {'slug': 'broken-hk-sessions', 'targets': [dict(prefix='hk', scope='hk_stock',
                                                       rule='session_schedule', market='XHKG')]}
    with pytest.raises(ValueError, match='broken question history'):
        site.question_series(hk, mr.records())


def test_history_tables_contain_exact_record_values_metadata_and_sources(text, manifest):
    records = {r.id: r for r in mr.records()}
    questions = {q['slug']: q for q in site.questions()}
    for p in question_pages(manifest):
        q = questions[p['slug']]
        expected_ids = {r.id for t in q['targets'] for r in target_records(t, records.values())}
        assert set(p['record_ids']) == expected_ids
        doc = Document(text[p['path']]).root
        rows = doc.find('table')[0].elements('tr')[1:]
        assert len(rows) == len(expected_ids)
        seen = set()
        for row in rows:
            cells = row.elements('td')
            rid = cells[5].plain()
            seen.add(rid)
            r = records[rid]
            assert decode_value(cells[2]) == r.value, (p['path'], rid)
            assert cells[0].plain() == r.effective_from
            assert cells[1].plain() == (r.effective_to or 'open')
            assert cells[4].plain() == r.verification
            assert cells[9].plain() == (r.unit or '')
            assert [(a.plain(), a.attrs['href']) for a in cells[6].find('a')] == [
                (s['title'], s['url']) for s in r.sources]
            zh = site.zh_names()
            assert cells[3].plain() == (site.zh_markets(zh, r.market) if p['lang'] == 'zh-CN' else r.market)
            assert cells[7].plain() == (zh['scope'][r.scope] if p['lang'] == 'zh-CN' else r.scope)
            assert cells[8].plain() == (zh['rule'][r.rule] if p['lang'] == 'zh-CN' else r.rule)
            # Markdown twins retain the raw value and complete source URLs too.
            md = text[p['md']]
            assert f'`{rid}`' in md and f'`{site.compact(r.value)}`' in md
            assert all(f'[{s["title"]}](<{s["url"]}>)' in md for s in r.sources)
        assert seen == expected_ids


def test_answers_match_faq_text_and_are_first_and_record_derived(text, manifest):
    questions = {q['slug']: q for q in site.questions()}
    for p in question_pages(manifest):
        doc = Document(text[p['path']]).root
        main = doc.find('main')[0]
        body = main.elements()
        h1_index = next(i for i, el in enumerate(body) if el.tag == 'h1')
        first = body[h1_index + 1]
        assert first.tag == 'p' and first.attrs == {'class': 'answer'}
        answer = first.plain()
        ld, = (json.loads(raw) for raw in LD_RE.findall(text[p['path']]))
        assert ld['@type'] == 'FAQPage' and ld['inLanguage'] == p['lang']
        entity, = ld['mainEntity']
        assert entity == {'@type': 'Question', 'name': body[h1_index].plain(),
                          'acceptedAnswer': {'@type': 'Answer', 'text': answer}}
        assert text[p['md']].split('\n\n', 2)[1] == answer
        zh = site.zh_names()
        chinese = p['lang'] == 'zh-CN'
        summarised = ('更早还有' if chinese else 'earlier values on record from') in answer
        for _, rs in site.question_series(questions[p['slug']], mr.records()):
            assert rs[0].effective_from in answer                       # where the history starts
            assert site.answer_value(rs[-1], zh, chinese) in answer      # the value in force
            for r in rs:                                                 # every value is a record's, in answer words
                assert summarised or site.answer_value(r, zh, chinese) in answer
            for x, y in zip(rs, rs[1:]):                                 # each change of value is dated
                if (x.scope, x.rule, x.value) != (y.scope, y.rule, y.value):
                    assert y.effective_from in answer or summarised
        digits = set(re.findall(r'\d+(?:\.\d+)?', answer))
        allowed = set()
        for _, rs in site.question_series(questions[p['slug']], mr.records()):
            for r in rs:
                allowed |= set(re.findall(r'\d+(?:\.\d+)?', ' '.join(
                    [site.answer_value(r, zh, chinese), r.effective_from, str(r.effective_to),
                     zh['scope'][r.scope], zh['rule'][r.rule], r.scope, r.rule])))   # labels may carry a date
        allowed |= set(re.findall(r'\d+(?:\.\d+)?', ' '.join(
            str(n) for n in range(1, 200))))                             # the count of summarised values
        assert digits <= allowed, digits - allowed                       # no number that is not from a record
        assert body[h1_index + 2].tag == 'h2'
        assert body[h1_index + 3].find('table')  # history immediately follows the answer


def test_hreflang_pairs_canonicals_languages_and_no_base_url_mode(built, manifest):
    base = 'https://example.org/rules/'
    paths = [p['path'] for p in question_pages(manifest)] + ['index.html', 'zh/index.html']
    for path in paths:
        doc = Document(built['based'][path].decode()).root
        assert doc.find('html')[0].attrs['lang'] == ('zh-CN' if path.startswith('zh/') else 'en')
        links = [n.attrs for n in doc.find('link')]
        assert [a['href'] for a in links if a.get('rel') == 'canonical'] == [base + path]
        alts = {a['hreflang']: a['href'] for a in links if a.get('rel') == 'alternate'}
        enpath = path.removeprefix('zh/')
        assert alts == {'en': base + enpath, 'zh-CN': base + 'zh/' + enpath, 'x-default': base + enpath}
        assert all(url.removeprefix(base) in built['based'] for url in alts.values())
        assert b'hreflang=' not in built['files'][path]
        assert b'rel="canonical"' not in built['files'][path]


def test_chinese_landing_uses_verbatim_opening_and_both_lists_are_complete(text):
    readme = Path(ROOT, 'README.zh-CN.md').read_text()
    opening = site.readme_opening(readme)
    assert opening and all(p in readme for p in opening)                 # verbatim
    for para in opening:
        assert '<p>' + site.md_inline(para) + '</p>' in text['zh/index.html']
    assert '以英文版为准' in readme and '以英文版为准' not in text['zh/index.html']   # a relative link is GitHub-only
    for q in site.questions():
        assert f'href="q/{q["slug"]}.html">{html.escape(q["zh"])}</a>' in text['zh/index.html']
        assert f'href="{q["slug"]}.html">{html.escape(q["en"])}</a>' in text['q/index.html']
    for pfx, name in site.zh_names()['family'].items():
        assert f'href="../{pfx}/index.html">{name}</a>' in text['zh/index.html']
    assert 'href="q/index.html"' in text['index.html'] and 'href="zh/index.html"' in text['index.html']


def test_question_gaps_and_fact_links_are_preserved(text, manifest):
    qs = {q['slug']: q for q in site.questions()}
    for p in question_pages(manifest):
        q = qs[p['slug']]
        expected = {(t['prefix'], g['gap_id']) for t in q['targets'] for g in mr.known_gaps(t['prefix'])
                    if (g['scope'], g['rule']) == (t['scope'], t['rule'])}
        assert {(g['prefix'], g['gap_id']) for g in p['question_gaps']} == expected
        for pfx, gid in expected:
            g = next(g for g in mr.known_gaps(pfx) if g['gap_id'] == gid)
            assert html.escape(g['reason']) in text[p['path']]
            assert site.cell_md(g['reason']) in text[p['md']]
        for t in q['targets']:
            fact = f'{t["prefix"]}/{t["scope"]}/{t["rule"]}'
            assert f'href="{site.rel(p["path"], fact + ".html")}"' in text[p['path']]
        assert 'pip install marina-rules' in text[p['path']] and 'mr.rule_at(' in text[p['md']]


def test_sitemap_covers_every_html_with_record_based_iso_lastmod(built, manifest):
    base = 'https://example.org/rules/'
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    root = ET.fromstring(built['based']['sitemap.xml'])
    dates = {}
    for url in root.findall('sm:url', ns):
        loc = url.findtext('sm:loc', namespaces=ns)
        lastmods = url.findall('sm:lastmod', ns)
        assert len(lastmods) == 1
        stamp = lastmods[0].text
        assert date.fromisoformat(stamp).isoformat() == stamp
        assert loc not in dates
        dates[loc] = stamp
    assert set(dates) == {base + path for path in built['based'] if path.endswith('.html')}
    records = mr.records()
    global_latest = max(r.recorded_at for r in records)
    qs = {q['slug']: q for q in site.questions()}
    for p in manifest['pages']:
        if p['kind'] == 'question':
            shown = {r.id: r for t in qs[p['slug']]['targets'] for r in target_records(t, records)}.values()
        elif p['kind'] in {'fact', 'scope'}:
            eligible = [r for r in records if r.file.startswith(p['prefix'] + '/') and r.scope == p['scope']]
            if p['kind'] == 'fact':
                shown = [r for r in eligible if r.rule == p['rule']]
            else:
                shown = [max((r for r in eligible if (r.market, r.rule) == key),
                             key=lambda r: (r.effective_from, r.market, r.id))
                         for key in {(r.market, r.rule) for r in eligible}]
        else:
            shown = []
        assert dates[base + p['path']] == max((r.recorded_at for r in shown), default=global_latest)


def test_questions_listed_as_markdown_and_based_build_deterministic(built, manifest):
    assert built['files'] == built['other']
    assert site.build('https://example.org/rules/') == built['based']
    assert manifest['counts']['question_pages'] == 2 * manifest['counts']['questions']
    llms = built['based']['llms.txt'].decode()
    assert '## Questions\n' in llms and 'https://example.org/rules/zh/index.html' in llms
    for p in question_pages(manifest):
        assert f'](https://example.org/rules/{p["md"]})' in llms
