#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import json, time
import pandas as pd
import akshare as ak

OUT=Path('results/top100_spot_refresh');OUT.mkdir(parents=True,exist_ok=True)
CODES=pd.read_csv('tools/top100_codes.csv',dtype={'code':str})

def retry(fn,n=4):
    e=None
    for i in range(n):
        try:return fn()
        except Exception as x:e=x;time.sleep(1.5*(i+1))
    raise e

def sf(x):
    try:return float(str(x).replace(',','').replace('%',''))
    except:return None

def ind(code):
    o={'code':code}
    try:
        d=retry(lambda:ak.stock_individual_info_em(symbol=code,timeout=60),3)
        m={str(r['item']):r['value'] for _,r in d.iterrows()}
        o.update({'individual_price':sf(m.get('最新')),'total_shares':sf(m.get('总股本')),'float_shares':sf(m.get('流通股')),'individual_market_cap':sf(m.get('总市值')),'individual_float_market_cap':sf(m.get('流通市值')),'individual_industry':m.get('行业'),'listing_date':m.get('上市时间')})
    except Exception as e:o['individual_error']=f'{type(e).__name__}: {e}'
    try:
        h=retry(lambda:ak.stock_zh_a_hist(symbol=code,period='daily',start_date='20260720',end_date=datetime.now().strftime('%Y%m%d'),adjust='',timeout=60),3)
        if h is not None and not h.empty:
            r=h.iloc[-1];o.update({'hist_date':str(r.get('日期')),'hist_close':sf(r.get('收盘')),'hist_change_pct':sf(r.get('涨跌幅')),'hist_turnover':sf(r.get('换手率')),'hist_amount':sf(r.get('成交额'))})
    except Exception as e:o['hist_error']=f'{type(e).__name__}: {e}'
    return o

def main():
    spot=None;errors=[]
    for name,fn in [('all',ak.stock_zh_a_spot_em),('comment',ak.stock_comment_em)]:
        try:
            x=retry(fn,5);x.to_csv(OUT/f'{name}_raw.csv',index=False,encoding='utf-8-sig')
            if name=='all': spot=x
        except Exception as e:errors.append(f'{name}: {e}')
    rows=[]
    with ThreadPoolExecutor(max_workers=10) as ex:
        fs={ex.submit(ind,c):c for c in CODES.code}
        for i,f in enumerate(as_completed(fs),1):
            rows.append(f.result())
            if i%20==0:print(i)
    indf=pd.DataFrame(rows)
    base=CODES.merge(indf,on='code',how='left')
    if spot is not None and not spot.empty:
        spot=spot.copy();spot['代码']=spot['代码'].astype(str).str.zfill(6)
        use=['代码','最新价','涨跌幅','换手率','量比','市盈率-动态','市净率','总市值','流通市值','60日涨跌幅','年初至今涨跌幅']
        base=base.merge(spot[[c for c in use if c in spot.columns]],left_on='code',right_on='代码',how='left')
    base['final_price']=pd.to_numeric(base.get('最新价'),errors='coerce').fillna(pd.to_numeric(base['individual_price'],errors='coerce')).fillna(pd.to_numeric(base['hist_close'],errors='coerce'))
    base['final_market_cap']=pd.to_numeric(base.get('总市值'),errors='coerce').fillna(pd.to_numeric(base['individual_market_cap'],errors='coerce'))
    base['final_float_market_cap']=pd.to_numeric(base.get('流通市值'),errors='coerce').fillna(pd.to_numeric(base['individual_float_market_cap'],errors='coerce'))
    base.to_csv(OUT/'top100_spot_refresh.csv',index=False,encoding='utf-8-sig')
    diag={'time':datetime.now().astimezone().isoformat(),'all_spot_rows':0 if spot is None else len(spot),'final_price':int(base.final_price.notna().sum()),'final_market_cap':int(base.final_market_cap.notna().sum()),'errors':errors}
    (OUT/'diagnostics.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(diag,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
