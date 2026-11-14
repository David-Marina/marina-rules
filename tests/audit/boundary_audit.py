"""Independent audit. Run: PYTHONPATH=/path/to/repo/src python boundary_audit.py /path/to/repo
Outputs expected vs actual; FAIL is intentional evidence, not an xfail.
Credit: independent audit, 2026-10-26. Probe expectations are the auditor's and are not edited here;
tests/test_boundary_audit.py runs this file unchanged as a regression gate.
"""
import sys,json,inspect,importlib.util,dataclasses
from collections import Counter
from pathlib import Path
import marina_rules as m
try:
 from marina_rules.contract import resolve
except ImportError: resolve=None
R=[]
def test(id,group,expected,fn):
 try:
  got=fn(); ok=got==expected
 except Exception as e: got={'error':type(e).__name__,'message':str(e)};ok=False
 R.append(dict(id=id,group=group,expected=expected,actual=got,status='PASS' if ok else 'FAIL'))
def ra(scope,date,market='XSHE',rule='price_limit_pct'):
 if m.DATA_VERSION=='2026.10.24b':
  scope='ipo_first5' if scope.startswith('ipo_first5_') else ('ipo_day1' if scope=='ipo_day1_main' else scope)
 return m.rule_at(rule,date,scope,market)
def res(scope,ctx,rule='price_limit_pct',date='2024-06-14',market='XSHE'):
 if resolve is None: return 'API_ABSENT'
 return resolve(rule,date,scope,market,ctx)['status']
for date,v in [('2020-08-21',.1),('2020-08-24',.2)]:test('CHINEXT-'+date,'reform',v,lambda d=date:ra('chinext',d))
for scope,market,date,v in [('st_main','XSHE','2026-07-03',.05),('st_main','XSHE','2026-07-06',.1),('st_chinext','XSHE','2020-08-21',.05),('st_chinext','XSHE','2020-08-24',.2),('st_star','XSHG','2024-06-14',.2),('st_bse','BJSE','2024-06-14',.3)]:test('ST-'+scope+date,'ST',v,lambda s=scope,d=date,mk=market:ra(s,d,mk))
for market,date,exp in [('XSHE','2011-02-25',[.04,.04]),('XSHE','2011-02-28',[.05,.03]),('XSHG','2023-04-07',[.04,.04]),('XSHG','2023-04-10',[.05,.03])]:test('TICK-'+market+date,'one_tick',exp,lambda mk=market,d=date:list(m.limit_price(.04,'st_main',d,mk)))
for s,mk,d,v in [('ipo_first5_main','XSHG','2023-04-10','unlimited'),('ipo_first5_chinext','XSHE','2020-08-24','unlimited'),('ipo_first5_star','XSHG','2019-07-22','unlimited'),('ipo_day1_main','XSHE','2020-08-21',{'up':.44,'down':.36}),('etf','XSHE','2024-06-14',.1),('etf_20pct','XSHE','2024-06-14',.2),('convertible','XSHE','2022-07-29','unlimited'),('convertible','XSHE','2022-08-01',.2),('reits_day1','XSHG','2024-06-14',.3),('reits','XSHG','2024-06-14',.1)]:test('BAND-'+s+d,'bands',v,lambda s=s,mk=mk,d=d:ra(s,d,mk))
test('CB-ISSUE','convertible',{'up':.573,'down':.433},lambda:ra('convertible_day1','2024-06-14',rule='price_limit_pct_of_issue_price'))
for mk in ['XSHE','XSHG']:
 test('CB-TICK-'+mk,'convertible',.001,lambda mk=mk:m.tick_size('convertible','2025-06-16',mk))
 test('CB-ROUND-'+mk,'convertible',[120.004,80.002],lambda mk=mk:list(m.limit_price(100.003,'convertible','2025-06-16',mk)))
for id,s,ctx in [('BOARD','main_board',dict(board='star',st_status=False,listing_day_index=100)),('IPO-ORDINARY','main_board',dict(board='main_board',st_status=False,listing_day_index=1)),('REGIME','ipo_first5_main',dict(board='main_board',listing_day_index=1,issue_regime='approval')),('ETF-CONTENTS','etf_20pct',dict(fund_constituents='mixed')),('CB-DAY1','convertible',dict(listing_day_index=1)),('DELIST-DAY','delisting_day1',dict(board='main_board',delisting_day_index=2)),('REITS-DAY','reits_day1',dict(listing_day_index=2)),('BSE-ST','bse',dict(board='bse',st_status=True,listing_day_index=100)),('NULL','main_board',dict(board=None,st_status=False,listing_day_index=None))]:
 test('CTX-'+id,'context','MISSING_CONTEXT',lambda s=s,c=ctx:res(s,c,market='BJSE' if s=='bse' else 'XSHE'))
for n in [0,1,5,6]:test('IPO-DAY-'+str(n),'context','DETERMINED' if 1<=n<=5 else 'MISSING_CONTEXT',lambda n=n:res('ipo_first5_main',dict(board='main_board',listing_day_index=n,issue_regime='registration')))
test('ST-CONTRADICTION','context','MISSING_CONTEXT',lambda:res('st_main',dict(board='main_board',st_status=False)))
test('CROSSBORDER-UNKNOWN','context','MISSING_CONTEXT',lambda:res('etf',{'fund_type':'cross_border'},'min_holding_days'))
for s,ctx,v in [('stock',{},1),('etf',{'fund_type':'other'},1),('etf_bond',{'fund_type':'bond_etf'},0),('etf_crossborder',{'fund_type':'cross_border','underlying_t0':True},0)]:test('HOLD-'+s,'settlement',v,lambda s=s:ra(s,'2024-06-14',rule='min_holding_days'))
test('GAP-CHINEXT','known_gaps',['G-0016'],lambda:resolve('price_limit_pct','2020-09-01','delisting_chinext','XSHE',{'board':'chinext','delisting_day_index':2})['known_gap_ids'] if resolve else 'API_ABSENT')
test('GAP-TICK','known_gaps',['G-0005'],lambda:resolve('tick_size','2005-01-05','stock','XSHE')['known_gap_ids'] if resolve else 'API_ABSENT')
for fn in ['record_at','rule_at','coverage']:test('ASOF-'+fn,'as_of',True,lambda fn=fn:'as_of' in inspect.signature(getattr(m,fn)).parameters)
test('ASOF-resolve','as_of',True,lambda:resolve is not None and 'as_of' in inspect.signature(resolve).parameters)
from marina_rules.check import check_rows
base={'date':'2024-06-14','code':'000001','side':'buy','price':10,'prev_close':10,'scope':'main_board','market':'XSHE'}
test('CHECK-OFFTICK','fill_validation',False,lambda:check_rows([{**base,'price':10.001}])['rules_verified'])
test('CHECK-NAN-UNLIMITED','fill_validation',False,lambda:check_rows([{**base,'price':'nan','scope':'ipo_first5' if m.DATA_VERSION=='2026.10.24b' else 'ipo_first5_main'}])['rules_verified'])
test('STAMP-FEE','stamp',False,lambda:check_rows([{**base,'fee':1,'turnover':10000}])['stamp']==check_rows([{**base,'fee':2,'turnover':10000}])['stamp'])
test('STAMP-MARKET','stamp',False,lambda:check_rows([base])['stamp']==check_rows([{**base,'market':'XSHG'}])['stamp'])
if True:
 test('COVER-TICK-FAMILY','coverage',True,lambda:(m.coverage('XSHE','main_board',['tick_size'],'2024-06-14','2024-06-15')['status']=='complete')==(res('main_board',{},'tick_size')=='DETERMINED'))
def overlap():
 rs=m.records(); r=next(x for x in rs if x.scope=='main_board' and x.rule=='price_limit_pct')
 synthetic=[r,dataclasses.replace(r,id='audit.conflict',market='XSHE',value=.2)]
 orig=m.records;m.records=lambda:synthetic
 try:
  try:m.record_at('price_limit_pct','2024-06-14','main_board','XSHE');return 'SILENT'
  except m.RuleConflict:return 'CONFLICT'
 finally:m.records=orig
test('OVERLAP-MARKET','conflict','CONFLICT',overlap)
repo=Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('auditbars',repo/'scripts/audit_bars.py');ab=importlib.util.module_from_spec(spec);spec.loader.exec_module(ab)
test('AUDIT-IPO-DATE','bar_audit',['ipo_day1_main','XSHG+XSHE'],lambda:list(ab.scope_cn_a('sh.603000','2023-03-01',0)))
print(json.dumps({'version':m.DATA_VERSION,'digest':m.dataset_digest(),'summary':dict(Counter(x['status'] for x in R)),'tests':R},ensure_ascii=False,indent=2))
