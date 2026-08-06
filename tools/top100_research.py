#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, math, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import akshare as ak
import numpy as np
import pandas as pd

OUT=Path('results/top100_research'); OUT.mkdir(parents=True,exist_ok=True)
NOW=datetime.now().astimezone(); START=(NOW-timedelta(days=520)).strftime('%Y%m%d'); END=NOW.strftime('%Y%m%d')
STOCKS=pd.read_csv('tools/top100_codes.csv',dtype={'code':str}).to_dict('records')
POS=['增长','大增','预增','扭亏','盈利','中标','订单','签约','合作','突破','量产','扩产','投产','涨价','回购','增持','分红','超预期','获批','国产替代','份额提升','景气','加速','领先','成功']
NEG=['下降','下滑','预减','亏损','续亏','减持','问询','立案','调查','处罚','诉讼','仲裁','逾期','违约','终止','失败','风险提示','退市','ST','停产','事故','质押','解禁','商誉减值','业绩不及','监管']
RISK=['立案','调查','退市','ST','重大诉讼','债务逾期','无法表示意见','非标审计']

def sf(x:Any):
    try:
        if x is None or pd.isna(x): return None
        if isinstance(x,str):
            x=x.strip().replace(',','').replace('%','')
            if x in ('','-','--','None','nan'): return None
        return float(x)
    except: return None

def retry(fn,n=4):
    err=None
    for i in range(n):
        try:return fn()
        except Exception as e: err=e; time.sleep(1.5*(i+1))
    raise err

def ret(s,n):
    s=s.dropna(); return float(s.iloc[-1]/s.iloc[-1-n]-1) if len(s)>n else None

def hist(code):
    o={'code':code}
    try:
        d=retry(lambda:ak.stock_zh_a_hist(symbol=code,period='daily',start_date=START,end_date=END,adjust='qfq',timeout=60))
        if d is None or d.empty: return {**o,'hist_error':'empty'}
        for c in ['收盘','成交额','换手率']: d[c]=pd.to_numeric(d.get(c),errors='coerce')
        c=d['收盘'].dropna(); dr=c.pct_change().dropna()
        o.update({'hist_last_date':str(d.iloc[-1].get('日期','')),'ret_5d':ret(c,5),'ret_20d':ret(c,20),'ret_60d':ret(c,60),'ret_120d':ret(c,120),'ret_250d':ret(c,250)})
        for n in [20,60,120,250]:
            if len(c)>=n:o[f'ma_{n}']=float(c.tail(n).mean());o[f'price_to_ma{n}']=float(c.iloc[-1]/c.tail(n).mean()-1)
        if len(dr)>=20:o['vol_20d_ann']=float(dr.tail(20).std()*np.sqrt(252))
        if len(dr)>=60:o['vol_60d_ann']=float(dr.tail(60).std()*np.sqrt(252))
        if len(c)>=120:
            q=c.tail(120);o['max_drawdown_120d']=float((q/q.cummax()-1).min())
        o['avg_amount_20d']=float(d['成交额'].dropna().tail(20).mean())
        o['avg_turnover_20d']=float(d['换手率'].dropna().tail(20).mean())
        o['last_60_close']=[round(float(x),4) for x in c.tail(60)]
    except Exception as e:o['hist_error']=f'{type(e).__name__}: {e}'
    return o

def news(code):
    o={'code':code};items=[]
    try:
        d=retry(lambda:ak.stock_news_em(symbol=code),3)
        c7=pd.Timestamp(NOW.replace(tzinfo=None))-pd.Timedelta(days=7);c30=pd.Timestamp(NOW.replace(tzinfo=None))-pd.Timedelta(days=30)
        scores=[];p=n=z=r=k7=k30=0
        for _,x in d.iterrows():
            title=str(x.get('新闻标题','') or '');body=str(x.get('新闻内容','') or '')[:500];txt=title+' '+body
            ph=sum(w in txt for w in POS);nh=sum(w in txt for w in NEG);rh=sum(w in txt for w in RISK);sc=ph-1.25*nh-2*rh
            item={'code':code,'published':str(x.get('发布时间','')),'title':title,'source':str(x.get('文章来源','') or ''),'url':str(x.get('新闻链接','') or ''),'sentiment':sc,'positive_hits':ph,'negative_hits':nh,'risk_hits':rh};items.append(item)
            ts=pd.to_datetime(x.get('发布时间'),errors='coerce')
            if pd.notna(ts) and ts>=c30:
                k30+=1;k7+=int(ts>=c7);scores.append(sc);r+=int(rh>0)
                if sc>.25:p+=1
                elif sc<-.25:n+=1
                else:z+=1
        o.update({'news_count_7d':k7,'news_count_30d':k30,'news_pos_30d':p,'news_neg_30d':n,'news_neutral_30d':z,'news_risk_30d':r,'news_sentiment_30d':float(np.mean(scores)) if scores else 0,'latest_headlines':' || '.join(i['title'] for i in items[:5]),'latest_news_urls':' || '.join(i['url'] for i in items[:5])})
    except Exception as e:o['news_error']=f'{type(e).__name__}: {e}'
    return o,items

def spot():
    a=[]
    for f in [ak.stock_sh_a_spot_em,ak.stock_sz_a_spot_em,ak.stock_bj_a_spot_em]:
        try:a.append(retry(f,5))
        except Exception as e:print('spot part error',e)
    d=pd.concat(a,ignore_index=True);d['代码']=d['代码'].astype(str).str.zfill(6);return d.drop_duplicates('代码')

def perfs():
    out={}
    for k,fn in [('h1_report',lambda:ak.stock_yjbb_em(date='20260630')),('h1_quick',lambda:ak.stock_yjkb_em(date='20260630')),('h1_forecast',lambda:ak.stock_yjyg_em(date='20260630')),('q1_report',lambda:ak.stock_yjbb_em(date='20260331')),('fy25_report',lambda:ak.stock_yjbb_em(date='20251231'))]:
        try:
            d=retry(fn);d['股票代码']=d['股票代码'].astype(str).str.zfill(6);out[k]=d;d.to_csv(OUT/f'{k}.csv',index=False,encoding='utf-8-sig')
        except Exception as e:(OUT/f'{k}_error.txt').write_text(str(e),encoding='utf-8')
    return out

def attach_perf(o,tables):
    code=o['code']
    for k in ['h1_report','h1_quick','h1_forecast','q1_report','fy25_report']:
        d=tables.get(k)
        if d is None:continue
        h=d[d['股票代码']==code]
        if h.empty:continue
        x=h.iloc[0].to_dict();o['performance_source']=k;o['performance_raw']=json.dumps(x,ensure_ascii=False,default=str)
        for c,v in x.items():
            c=str(c)
            if '营业' in c and '同比' in c and o.get('perf_revenue_yoy') is None:o['perf_revenue_yoy']=sf(v)
            if '净利润' in c and '同比' in c and o.get('perf_net_profit_yoy') is None:o['perf_net_profit_yoy']=sf(v)
            if c in ['净利润-净利润','净利润'] and o.get('perf_net_profit') is None:o['perf_net_profit']=sf(v)
            if c in ['营业总收入-营业总收入','营业收入-营业收入','营业总收入'] and o.get('perf_revenue') is None:o['perf_revenue']=sf(v)
            if '业绩变动幅度' in c:
                if '下限' in c:o['forecast_growth_low']=sf(v)
                elif '上限' in c:o['forecast_growth_high']=sf(v)
                else:o['forecast_growth_mid']=sf(v)
            if '业绩变动原因' in c:o['forecast_reason']=str(v)[:1200]
        break

def pct(s,good=True):
    s=pd.to_numeric(s,errors='coerce');r=s.rank(pct=True);return (r if good else 1-r).fillna(.5)

def score(d):
    g=.45*pct(d.get('perf_revenue_yoy'))+.55*pct(d.get('perf_net_profit_yoy'))
    m=.15*pct(d.get('ret_5d'))+.25*pct(d.get('ret_20d'))+.35*pct(d.get('ret_60d'))+.25*pct(d.get('ret_120d'))
    v=.55*pct(d.get('pe_dynamic'),False)+.45*pct(d.get('pb'),False)
    s=.7*pct(d.get('news_sentiment_30d'))+.3*pct(d.get('news_count_30d'))
    q=.55*pct(d.get('perf_net_profit_yoy'))+.45*pct(d.get('perf_revenue_yoy'))
    liq=.65*pct(d.get('avg_amount_20d'))+.35*pct(d.get('avg_turnover_20d'))
    risk=.45*pct(d.get('vol_60d_ann'),False)+.35*pct(d.get('max_drawdown_120d'))+.2*pct(d.get('news_risk_30d'),False)
    d['growth_score']=g*100;d['momentum_score']=m*100;d['valuation_score']=v*100;d['sentiment_score']=s*100;d['quality_score']=q*100;d['liquidity_score']=liq*100;d['risk_control_score']=risk*100
    d['quant_score']=(.2*g+.23*m+.14*v+.1*s+.12*q+.08*liq+.13*risk)*100
    d.loc[d['name'].str.contains('ST',case=False,na=False),'quant_score']-=20;d['quant_score']-=pd.to_numeric(d.get('news_risk_30d'),errors='coerce').fillna(0).clip(0,5)*2
    d['quant_score']=d['quant_score'].clip(0,100);d['quant_rank']=d['quant_score'].rank(ascending=False,method='min').astype(int);return d

def main():
    sp=spot();sp.to_csv(OUT/'spot_all_a.csv',index=False,encoding='utf-8-sig');sm={r['代码']:r for _,r in sp.iterrows()};tables=perfs();records=[]
    for s in STOCKS:
        o=dict(s);x=sm.get(s['code'],{});o.update({'snapshot_time':NOW.isoformat(),'price':sf(x.get('最新价')),'daily_change_pct':sf(x.get('涨跌幅')),'turnover':sf(x.get('换手率')),'volume_ratio':sf(x.get('量比')),'pe_dynamic':sf(x.get('市盈率-动态')),'pb':sf(x.get('市净率')),'market_cap':sf(x.get('总市值')),'float_market_cap':sf(x.get('流通市值')),'spot_ret_60d_pct':sf(x.get('60日涨跌幅')),'spot_ytd_pct':sf(x.get('年初至今涨跌幅'))});attach_perf(o,tables);records.append(o)
    H={};N={};allnews=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(hist,s['code']):('h',s['code']) for s in STOCKS};fs.update({ex.submit(news,s['code']):('n',s['code']) for s in STOCKS})
        for i,f in enumerate(as_completed(fs),1):
            typ,code=fs[f]
            try:
                if typ=='h':H[code]=f.result()
                else:N[code],items=f.result();allnews.extend(items)
            except Exception as e:(H if typ=='h' else N)[code]={'code':code,f'{typ}_error':str(e)}
            if i%20==0:print('done',i,'/',len(fs))
    for o in records:o.update(H.get(o['code'],{}));o.update(N.get(o['code'],{}))
    d=score(pd.DataFrame(records)).sort_values('quant_rank');d.drop(columns=['last_60_close'],errors='ignore').to_csv(OUT/'top100_snapshot.csv',index=False,encoding='utf-8-sig');d.to_json(OUT/'top100_snapshot.json',orient='records',force_ascii=False,indent=2);pd.DataFrame(allnews).to_csv(OUT/'top100_news.csv',index=False,encoding='utf-8-sig')
    diag={'snapshot_time':NOW.isoformat(),'stock_count':len(d),'spot_matches':int(d.price.notna().sum()),'history_success':int(d.get('hist_error',pd.Series([None]*len(d))).isna().sum()),'news_success':int(d.get('news_error',pd.Series([None]*len(d))).isna().sum()),'performance_tables':{k:len(v) for k,v in tables.items()},'top_quant':d[['quant_rank','code','name','quant_score']].head(20).to_dict('records')};(OUT/'diagnostics.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(diag,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
