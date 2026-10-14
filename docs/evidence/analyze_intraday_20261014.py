"""Reproducible descriptive pilot; stdlib analysis, no trading/backtest engine."""
import json, math, statistics, hashlib, datetime, pathlib

ROOT=pathlib.Path(__file__).resolve().parent
raw=json.loads((ROOT/'intraday_raw_20261014.json').read_text())
CUT=raw['cutoff_ms']; STEP=300000; START=CUT-86400000
def utc(ms): return datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).isoformat()
def quant(values,p):
    if not values:return None
    x=sorted(values);i=(len(x)-1)*p;a=int(i);return x[a]+(x[min(a+1,len(x)-1)]-x[a])*(i-a)

allrows={}
for sym,bars in raw['klines'].items():
    rows=[{'t':int(b[0]),'ct':int(b[6]),'o':float(b[1]),'h':float(b[2]),'l':float(b[3]),'c':float(b[4]),'q':float(b[7]),'buyq':float(b[10])} for b in bars if int(b[6])<CUT]
    assert len({r['t'] for r in rows})==len(rows)
    assert all(rows[i+1]['t']-rows[i]['t']==STEP for i in range(len(rows)-1)),sym
    assert all(r['l']<=min(r['o'],r['c'])<=max(r['o'],r['c'])<=r['h'] and 0<=r['buyq']<=r['q']*1.000001 for r in rows),sym
    for i,r in enumerate(rows):
        prev=[z['q'] for z in rows[max(0,i-72):i]]
        med=statistics.median(prev) if len(prev)==72 else None
        r['rvol']=r['q']/med if med and med>0 else None
        r['r15']=100*(r['c']/rows[i-3]['c']-1) if i>=3 else None
        r['buy_share']=r['buyq']/r['q'] if r['q'] else None
    allrows[sym]=rows

episodes=[]; summaries=[]
for pick in raw['picks']:
    sym=pick['symbol'];side=1 if float(pick['priceChangePercent'])>0 else -1
    rows=allrows[sym];idx=[i for i,r in enumerate(rows) if START<=r['t']<CUT];day=[rows[i] for i in idx]
    assert len(day)==288,(sym,len(day))
    best=None;anchor=0
    for j,r in enumerate(day):
        if side*math.log(r['c'])<side*math.log(day[anchor]['c']):anchor=j
        m=side*100*(r['c']/day[anchor]['c']-1)
        if best is None or m>best[0]:best=(m,anchor,j)
    move,a,p=best;peak=day[p]
    correction=next((r for r in day[p+1:] if side*100*(r['c']/peak['c']-1)<=-2),None)
    corrective_minutes=(correction['ct']-peak['ct'])/60000 if correction else None
    last_alert=-10**20;local=[]
    for i in idx:
        r=rows[i]
        if r['rvol'] is None or side*r['r15']<2 or r['rvol']<3 or r['ct']-last_alert<3600000:continue
        last_alert=r['ct']
        if i+1>=len(rows):
            local.append({'symbol':sym,'signal_ct':r['ct'],'entry_missing':True});continue
        entry=rows[i+1];ep={'symbol':sym,'side':'LONG-study' if side==1 else 'SHORT-study','signal_ct':r['ct'],'signal_utc':utc(r['ct']),'entry_t':entry['t'],'entry_open':entry['o'],'rvol':r['rvol'],'return15_signal':r['r15'],'taker_buy_share':r['buy_share']}
        for minutes in [5,15,30,60,120,240]:
            target=entry['t']+minutes*60000
            f=next((z for z in rows[i+1:] if z['ct']+1==target),None)
            ep['gross_directional_%dm'%minutes]=side*100*(f['c']/entry['o']-1) if f else None
        future=[z for z in rows[i+1:] if z['ct']+1<=entry['t']+240*60000]
        win=next((z for z in future if side*100*(z['c']/entry['o']-1)>=2),None)
        loss=next((z for z in future if side*100*(z['c']/entry['o']-1)<=-1),None)
        ep['first_close_plus2_min']=(win['ct']+1-entry['t'])/60000 if win else None
        ep['first_close_minus1_min']=(loss['ct']+1-entry['t'])/60000 if loss else None
        ep['available_forward_min']=len(future)*5
        ep['barrier_result']=('plus2-first' if win and (not loss or win['ct']<loss['ct']) else 'minus1-first' if loss else 'neither-full-window' if len(future)==48 else 'censored')
        best_px=entry['o']; pull=None; peak_at=entry['t']; reclaimed=None
        for z in future:
            if side*(z['c']-best_px)>0:best_px=z['c'];peak_at=z['ct']
            if side*100*(best_px/entry['o']-1)>=1 and side*100*(z['c']/best_px-1)<=-1:
                pull=z;break
        if pull:
            aft=[z for z in future if pull['ct']<z['ct']<=pull['ct']+60*60000]
            reclaimed=next((z for z in aft if side*100*(z['c']/best_px-1)>=.1),None)
            ep['pullback']={'pullback_utc':utc(pull['ct']),'from_peak_min':(pull['ct']-peak_at)/60000,'reclaim_after_min':(reclaimed['ct']-pull['ct'])/60000 if reclaimed else None,'outcome':'reclaimed' if reclaimed else 'not_reclaimed_60m' if aft and aft[-1]['ct']>=pull['ct']+60*60000 else 'censored'}
        else:ep['pullback']=None
        local.append(ep)
    episodes.extend(local)
    complete=[e for e in local if e.get('gross_directional_60m') is not None]
    biggest=max(day,key=lambda r:r['q'])
    summaries.append({'symbol':sym,'direction':'up' if side==1 else 'down','ticker24_pct':float(pick['priceChangePercent']),'ticker_quote_volume':float(pick['quoteVolume']),'closed24_pct':100*(day[-1]['c']/day[0]['o']-1),'retrospective_best_directional_move_pct':move,'retrospective_start_utc':utc(day[a]['ct']),'retrospective_peak_utc':utc(peak['ct']),'rise_fall_duration_min':(peak['ct']-day[a]['ct'])/60000,'first_2pct_countermove_after_peak_min':corrective_minutes,'post_peak_available_min':(day[-1]['ct']-peak['ct'])/60000,'countermove_censored':correction is None,'max_5m_quote_volume':biggest['q'],'max_5m_volume_utc':utc(biggest['ct']),'rvol_at_max_volume':biggest['rvol'],'buy_share_at_max_volume':biggest['buy_share'],'max_rvol':max(r['rvol'] for r in day if r['rvol'] is not None),'alerts':len(local),'alerts_60m_complete':len(complete),'median_gross_directional_60m':statistics.median([e['gross_directional_60m'] for e in complete]) if complete else None,'market_cap':'UNKNOWN: not a verified low-cap cohort'})

stats={}
for side in ['LONG-study','SHORT-study']:
    e=[e for e in episodes if e.get('side')==side];wins=[e for e in e if e['barrier_result']=='plus2-first'];losses=[e for e in e if e['barrier_result']=='minus1-first']
    stats[side]={'alerts':len(e),'plus2_first':len(wins),'minus1_first':len(losses),'neither_full':sum(z['barrier_result']=='neither-full-window' for z in e),'censored':sum(z['barrier_result']=='censored' for z in e),'winner_time_median_min':quant([z['first_close_plus2_min'] for z in wins],.5),'winner_time_q25_min':quant([z['first_close_plus2_min'] for z in wins],.25),'winner_time_q75_min':quant([z['first_close_plus2_min'] for z in wins],.75)}
    pb=[z['pullback'] for z in e if z.get('pullback')];stats[side]['pullbacks']={'n':len(pb),'reclaimed':sum(z['outcome']=='reclaimed' for z in pb),'not_reclaimed_60m':sum(z['outcome']=='not_reclaimed_60m' for z in pb),'censored':sum(z['outcome']=='censored' for z in pb),'reclaim_time_median_min':quant([z['reclaim_after_min'] for z in pb if z['outcome']=='reclaimed'],.5)}
out={'cutoff_utc':utc(CUT),'window_start_utc':utc(START),'n_assets':len(summaries),'controls':['BTCUSDT'],'universe_n':523,'bar_interval':'5m','retrieval_limit_per_symbol':1500,'closed_rows':{s:len(r) for s,r in allrows.items()},'selection':'top5_positive_bottom5_negative_ticker24; current survivors, retrospective selection bias; no market-cap filter certified','alert_rule':'return15m signed >=2%; current5m quote-volume / median(previous72x5m) >=3; 60m cooldown; entry next bar open; demonstration only','barrier_rule':'first CLOSE reaching directional +2% vs -1%, within 240m; no intrabar fill simulation; incomplete censored','summaries':summaries,'episodes':episodes,'alert_stats':stats}
(ROOT/'intraday_analysis_20261014.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'cutoff':out['cutoff_utc'],'summaries':summaries,'alert_stats':stats},indent=2))
