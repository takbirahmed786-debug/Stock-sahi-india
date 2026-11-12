import math, time, re, threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template_string
import yfinance as yf

app=Flask(__name__)
cache={}
lock=threading.Lock()
COMMON={"RELIANCE":"RELIANCE.NS","TCS":"TCS.NS","INFOSYS":"INFY.NS","ITC":"ITC.NS","HDFC BANK":"HDFCBANK.NS","ICICI BANK":"ICICIBANK.NS","SBI":"SBIN.NS","WIPRO":"WIPRO.NS","TATA MOTORS":"TATAMOTORS.NS","TATA STEEL":"TATASTEEL.NS","TATA POWER":"TATAPOWER.NS","BHARTI AIRTEL":"BHARTIARTL.NS","LT":"LT.NS","HAL":"HAL.NS","BEL":"BEL.NS","TITAN":"TITAN.NS","MARUTI":"MARUTI.NS","BAJAJ FINANCE":"BAJFINANCE.NS","AXIS BANK":"AXISBANK.NS","SUN PHARMA":"SUNPHARMA.NS","PIDILITE":"PIDILITIND.NS","TRENT":"TRENT.NS"}
def num(x):
    try:
        n=float(x)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError): return None
def percent(v):
    n=num(v)
    return round(n*100,2) if n is not None else None
def row(df, names, col=0):
    try:
        for name in names:
            if name in df.index:
                return num(df.loc[name].iloc[col])
    except Exception: pass
    return None
def growth(cur,old,years):
    if cur is None or old is None or cur<=0 or old<=0 or years<=0:return None
    return round(((cur/old)**(1/years)-1)*100,2)
def bucket(val, edges):
    if val is None:return None
    score=0
    for threshold,result in edges:
        if val>=threshold:score=result
    return score
def cached(key, ttl, fn):
    with lock:
        hit=cache.get(key)
        if hit and hit[0]>time.time():return hit[1]
    result=fn()
    with lock:
        cache[key]=(time.time()+ttl,result)
        if len(cache)>150:
            for k,v in list(cache.items()):
                if v[0]<time.time():del cache[k]
    return result
def build(symbol):
    ticker=yf.Ticker(symbol)
    info=ticker.info or {}
    price=num(info.get("currentPrice")) or num(info.get("regularMarketPrice"))
    hist=ticker.history(period="1y", interval="1wk", auto_adjust=True)
    points=[]
    try:
        for d,r in hist.iterrows():
            p=num(r["Close"])
            if p is not None:points.append({"date":str(d.date()),"close":round(p,2)})
    except Exception:pass
    if price is None and points:price=points[-1]["close"]
    if price is None:raise ValueError("Is stock ka valid market price nahi mila. Symbol verify karein.")
    financials=ticker.financials
    balance=ticker.balance_sheet
    cash=ticker.cashflow
    n=min(4, len(financials.columns)) if financials is not None else 0
    revenues=[row(financials,["Total Revenue","Operating Revenue"],i) for i in range(n)]
    profits=[row(financials,["Net Income","Net Income Common Stockholders"],i) for i in range(n)]
    years=n-1
    sales_growth=growth(revenues[0],revenues[-1],years) if n>1 else None
    profit_growth=growth(profits[0],profits[-1],years) if n>1 else None
    roe=percent(info.get("returnOnEquity"))
    opmargin=percent(info.get("operatingMargins"))
    rev_growth=percent(info.get("revenueGrowth"))
    debt_eq=num(info.get("debtToEquity"))
    if debt_eq is not None: debt_eq=round(debt_eq/100,2)
    cfo=row(cash,["Operating Cash Flow","Total Cash From Operating Activities"]) if cash is not None else None
    fcf=row(cash,["Free Cash Flow"]) if cash is not None else None
    eps=num(info.get("trailingEps"))
    pe=num(info.get("trailingPE"))
    if (pe is None or pe<=0) and eps is not None and eps>0: pe=round(price/eps,2)
    pb=num(info.get("priceToBook"))
    ebit=row(financials,["EBIT","Operating Income"]) if financials is not None else None
    assets=row(balance,["Total Assets"]) if balance is not None else None
    cl=row(balance,["Current Liabilities"]) if balance is not None else None
    roce=round(ebit/(assets-cl)*100,2) if ebit is not None and assets is not None and cl is not None and assets>cl else None
    sector=str(info.get("sector") or "")
    industry=str(info.get("industry") or "")
    financial=any(x in (sector+" "+industry).lower() for x in ["financial","bank","insurance","credit service","capital market","mortgage"])
    metrics={"sales_cagr":sales_growth,"profit_cagr":profit_growth,"latest_revenue_growth":rev_growth,"roe":roe,"roce":None if financial else roce,"operating_margin":opmargin,"debt_equity":None if financial else debt_eq,"operating_cash_flow":cfo,"free_cash_flow":fcf,"pe":pe,"pb":pb,"eps":eps,"market_cap":num(info.get("marketCap")),"dividend_yield":percent(info.get("dividendYield"))}
    groups=[
      ("Growth",25,[(sales_growth,[(-999,5),(0,35),(8,60),(12,80),(18,100)]),(profit_growth,[(-999,5),(0,35),(10,65),(15,85),(22,100)]),(rev_growth,[(-999,5),(0,35),(8,65),(15,85),(25,100)])]),
      ("Profitability",20,[(roe,[(-999,0),(0,20),(8,45),(12,65),(16,85),(22,100)]),(None if financial else roce,[(-999,0),(0,20),(10,50),(15,72),(20,90),(28,100)]),(opmargin,[(-999,0),(0,25),(5,48),(10,65),(18,88),(28,100)])]),
      ("Balance",20,[(None if financial or debt_eq is None else -debt_eq,[(-999,0),(-2,15),(-1,48),(-0.5,78),(-0.15,100)])]),
      ("Cashflow",15,[(None if financial or cfo is None else (1 if cfo>0 else 0),[(-999,0),(1,100)]),(None if financial or fcf is None else (1 if fcf>0 else 0),[(-999,0),(1,100)])]),
      ("Valuation",20,[(None if pe is None else -pe,[(-9999,5),(-75,18),(-50,35),(-35,55),(-25,78),(-15,90),(-9,100)])])
    ]
    categories=[]
    weighted=total=0
    for name,weight,checks in groups:
        available=[bucket(v,b) for v,b in checks]
        available=[v for v in available if v is not None]
        score=round(sum(available)/len(available)) if available else None
        categories.append({"name":name,"score":score,"weight":weight})
        if score is not None:weighted+=weight*score;total+=weight
    overall=round(weighted/total) if total else None
    essential=[sales_growth,profit_growth,roe,opmargin,pe,eps]
    if not financial:essential.extend([debt_eq,cfo,roce])
    coverage=round(sum(v is not None for v in essential)/len(essential)*100)
    positives=[];risks=[]
    if sales_growth is not None:
        (positives if sales_growth>=12 else risks if sales_growth<0 else []).append("Sales CAGR "+str(sales_growth)+"%")
    if profit_growth is not None:
        (positives if profit_growth>=15 else risks if profit_growth<0 else []).append("Profit CAGR "+str(profit_growth)+"%")
    if roe is not None:
        (positives if roe>=16 else risks if roe<8 else []).append("ROE "+str(roe)+"%")
    if not financial and debt_eq is not None:
        (positives if debt_eq<0.4 else risks if debt_eq>1.5 else []).append("Debt/Equity "+str(debt_eq))
    if not financial and cfo is not None:
        (positives if cfo>0 else risks).append("Operating cash flow "+("positive" if cfo>0 else "negative"))
    if pe is not None and pe>50:risks.append("High P/E "+str(round(pe,1))+". Peers se compare karein.")
    if profits and profits[0] is not None and profits[0]<0:risks.append("Latest annual net loss")
    if financial:signal="SPECIAL";reason="Bank/NBFC ke liye NPA, NIM aur capital adequacy check chahiye."
    elif coverage<65 or n<2 or overall is None:signal="INCOMPLETE";reason="Complete decision ke liye financial data insufficient hai."
    elif profits and profits[0] is not None and profits[0]<0 and cfo is not None and cfo<0:signal="AVOID";reason="Loss aur negative operating cash flow saath mein hain."
    elif overall<48 or len(risks)>=3:signal="AVOID";reason="Fundamental risk factors zyada hain."
    elif overall>=75 and not risks and pe is not None and pe<=35:signal="CONSIDER";reason="Initial screening positive hai. Valuation aur annual reports verify karke hi invest karein."
    else:signal="WAIT";reason="Valuation, profit trend ya risks ko aur check karna chahiye."
    scenarios=[]
    if eps is not None and eps>0 and pe is not None and 0<pe<120 and (profit_growth is not None or sales_growth is not None):
        base=sum(x for x in [profit_growth,sales_growth] if x is not None)/sum(x is not None for x in [profit_growth,sales_growth])
        base=max(-8,min(22,base))
        for label,g,m in [("Conservative",base-8,pe*0.65),("Base",base,pe*0.9),("Optimistic",base+6,pe*1.1)]:
            future=eps*((1+g/100)**3)*m
            scenarios.append({"name":label,"price":round(future,2),"return_pct":round((future/price-1)*100,1),"eps_growth":round(g,1)})
    return {"symbol":symbol,"company":info.get("longName") or info.get("shortName") or symbol,"sector":sector,"industry":industry,"price":price,"currency":info.get("currency") or "INR","quote_as_of":points[-1]["date"] if points else None,"checked_at":datetime.now(timezone.utc).isoformat(),"metrics":metrics,"categories":categories,"score":overall,"coverage":coverage,"signal":signal,"reason":reason,"positives":positives,"risks":risks,"scenarios":scenarios,"history":points,"financials":[{"period":str(financials.columns[i].date()) if hasattr(financials.columns[i],"date") else str(financials.columns[i]),"sales":revenues[i],"profit":profits[i]} for i in range(n)],"warnings":["Automated screening, investment advice nahi. Data delayed, missing ya inaccurate ho sakta hai.","Promoter pledging, auditor reports, NSE/BSE filings aur sector peers independently check karein.","Scenario prices illustrative hain, future target ya guaranteed returns nahi."]}

@app.get("/api/health")
def health():return jsonify({"ok":True,"name":"StockSahi India"})
@app.get("/api/search")
def search():
    q=(request.args.get("q") or "").strip()
    if not 2<=len(q)<=60:return jsonify({"error":"2 se 60 characters likhein"}),400
    def lookup():
        results=[]; seen=set()
        matched=COMMON.get(q.upper())
        if matched:results.append({"symbol":matched,"name":q.title()});seen.add(matched)
        if re.fullmatch(r"[A-Za-z0-9.\-]{2,30}",q):
            sym=q.upper() if q.upper().endswith((".NS",".BO")) else q.upper()+".NS"
            if sym not in seen:results.append({"symbol":sym,"name":q.upper()+" (NSE symbol verify karein)"});seen.add(sym)
        try:
            for x in yf.Search(q,max_results=10,news_count=0,raise_errors=False).quotes:
                sym=str(x.get("symbol") or "").upper()
                if sym.endswith((".NS",".BO")) and sym not in seen and re.fullmatch(r"[A-Z0-9.\-]{2,30}",sym):
                    results.append({"symbol":sym,"name":x.get("shortname") or x.get("longname") or sym});seen.add(sym)
        except Exception:pass
        return results[:12]
    return jsonify({"results":cached("search:"+q.upper(),3600,lookup)})
@app.get("/api/report")
def report():
    sym=(request.args.get("symbol") or "").upper().strip()
    if not re.fullmatch(r"[A-Z0-9.\-]{2,30}",sym):return jsonify({"error":"Valid NSE/BSE symbol likhein"}),400
    if not sym.endswith((".NS",".BO")):sym+=".NS"
    try:return jsonify(cached("report:"+sym,900,lambda:build(sym)))
    except ValueError as e:return jsonify({"error":str(e)}),404
    except Exception:
        app.logger.exception("Finance data provider unavailable")
        return jsonify({"error":"Market data abhi available nahi. Thodi der baad try karein."}),503
@app.get("/")
def home():return render_template_string(PAGE)
PAGE=r"""<!doctype html><html lang="hi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#081a24"><title>StockSahi India | Share Fundamental Analysis</title><meta name="description" content="Indian stock research and fundamental stock screening"><style>
:root{color-scheme:dark;--bg:#07151e;--panel:#102632;--border:#274552;--muted:#9db6bf;--text:#f1f8fa;--green:#36e3a1;--yellow:#ffd27a;--red:#fa8e95}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 75% -20%,#17463e 0%,#07151e 45%);color:var(--text);font:15px/1.5 system-ui,-apple-system,Arial}.wrap{max-width:1040px;margin:auto;padding:20px 16px 80px}header{display:flex;align-items:center;justify-content:space-between;gap:12px}a{color:var(--green)}.brand{font-size:22px;font-weight:850;letter-spacing:-.8px}.brand span{color:var(--green)}.pill{border:1px solid #3e6a65;border-radius:20px;color:var(--green);font-size:12px;padding:5px 9px}.hero{padding:46px 0 28px}.eyebrow{color:var(--green);font-weight:700;font-size:13px}.hero h1{font-size:clamp(30px,6vw,53px);line-height:1.12;letter-spacing:-1.6px;margin:12px 0}.hero p{color:var(--muted);max-width:620px}.searchbox{position:relative;display:flex;gap:10px;background:#112d39;padding:9px;border:1px solid #35605e;border-radius:16px;max-width:790px}.searchbox input{flex:1;min-width:0;background:none;border:0;color:white;font-size:16px;padding:10px;outline:none}.searchbox button,button.action{background:var(--green);border:0;color:#052016;border-radius:11px;padding:11px 18px;font-weight:850;cursor:pointer}.suggest{max-width:790px;background:#183541;border:1px solid #35605e;border-radius:12px;margin-top:7px;overflow:hidden;display:none}.suggest button{display:flex;width:100%;background:none;border:none;border-bottom:1px solid #30515b;text-align:left;color:var(--text);padding:12px 14px;cursor:pointer;justify-content:space-between;gap:12px}.suggest span{color:var(--muted)}.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.chips button{border-radius:22px;background:#14313b;color:#b6d6dc;border:1px solid #34515a;padding:8px 11px;cursor:pointer}.panel{background:linear-gradient(150deg,#132c36,#0e222e);border:1px solid var(--border);border-radius:17px;padding:20px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{background:#102a35;border:1px solid #294652;border-radius:13px;padding:14px}.metric small,.subtitle{color:var(--muted)}.metric b{display:block;font-size:22px;margin-top:7px}.top{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap}.score{height:105px;width:105px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--green) calc(var(--val)*1%),#28505a 0);flex-shrink:0}.score div{background:#102632;width:80px;height:80px;border-radius:50%;display:grid;place-items:center;font-size:25px;font-weight:850}.signal{display:inline-block;padding:6px 10px;border-radius:7px;background:#274a40;color:var(--green);font-weight:800}.WAIT,.INCOMPLETE,.SPECIAL{background:#463e27;color:var(--yellow)}.AVOID{background:#552b36;color:var(--red)}.section{font-size:19px;font-weight:750;margin:0 0 14px}.bars{display:grid;gap:13px}.barrow{display:grid;grid-template-columns:100px 1fr 40px;gap:10px;align-items:center}.bar{height:9px;background:#25434e;border-radius:10px;overflow:hidden}.bar i{display:block;height:100%;background:var(--green)}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}.items{padding-left:19px;margin:8px 0}.items li{margin:8px 0;color:#c4d9dc}.note{color:var(--muted);font-size:12px}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;white-space:nowrap}td,th{text-align:left;padding:12px 7px;border-bottom:1px solid #2b4650}th{color:var(--muted)}.chart{width:100%;height:210px}.scenario{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.scenario>div{background:#173540;border-radius:11px;padding:14px}.scenario strong{display:block;font-size:20px}.actions{display:flex;gap:10px;flex-wrap:wrap}button.secondary{border:1px solid #47656c;background:#183641;color:white;border-radius:10px;padding:11px 15px;cursor:pointer}#result{display:none}#status{color:var(--yellow);min-height:26px;margin-top:12px}.foot{color:var(--muted);font-size:12px;margin-top:40px}@media(max-width:700px){.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}.scenario{grid-template-columns:1fr}.metric b{font-size:19px}.searchbox{flex-wrap:wrap}.searchbox button{width:100%}.hero{padding:32px 0 17px}.score{width:90px;height:90px}.score div{width:70px;height:70px}}
@media print{body{background:white;color:#111}.searchbox,.chips,.actions,header,.foot{display:none!important}.panel,.metric{background:white;color:#111;border:1px solid #ddd}.subtitle,.note,small{color:#555!important}#result{display:block!important}.wrap{padding:0}}
</style></head><body><div class="wrap"><header><div class="brand">Stock<span>Sahi</span> India</div><span class="pill">Fundamental Research</span></header>
<section class="hero"><div class="eyebrow">INDIAN STOCK ANALYSIS</div><h1>Share kharidein, rukhein,<br>ya avoid karein?</h1><p>Company ke financials, debt, growth, valuation aur risk check karke practical research report dekhein. Signal automatic screening hai, personal investment advice nahi.</p><form class="searchbox" id="form"><input id="query" autocomplete="off" placeholder="Company name / NSE symbol, jaise RELIANCE" aria-label="Stock name"><button type="submit">Analyse Share →</button></form><div class="suggest" id="suggest"></div><div id="status" role="status"></div><div class="chips" id="chips"></div></section>
<div id="result"><div class="panel"><div class="top"><div><div class="eyebrow" id="symbol"></div><h2 id="company" style="margin:5px 0;font-size:29px"></h2><div class="subtitle" id="sector"></div><div style="font-size:29px;font-weight:800;margin-top:14px" id="price"></div><div class="note" id="asof"></div></div><div class="score" id="score"><div id="scoretxt"></div></div></div><div style="margin-top:18px"><div id="signal" class="signal"></div><p id="reason" style="color:#cbdde0"></p><p id="coverage" class="note"></p></div><div class="actions"><button class="secondary" onclick="window.print()">Save PDF / Print</button><button class="secondary" onclick="shareReport()">Share Report</button></div></div>
<div class="grid" id="metrics"></div>
<div class="two"><div class="panel"><h3 class="section">Fundamental Score</h3><div class="bars" id="bars"></div></div><div class="panel"><h3 class="section">1-year Share Price</h3><svg viewBox="0 0 500 210" preserveAspectRatio="none" class="chart" id="chart"><text x="15" y="100" fill="#a9c9ce">Chart unavailable</text></svg><p class="note">Historical performance future return guarantee nahi karta.</p></div></div>
<div class="two"><div class="panel"><h3 class="section" style="color:var(--green)">Positive Points</h3><ul class="items" id="positive"></ul></div><div class="panel"><h3 class="section" style="color:var(--yellow)">Risk / Concern</h3><ul class="items" id="risks"></ul></div></div>
<div class="panel"><h3 class="section">3-year Illustrative Scenarios</h3><div class="scenario" id="scenarios"></div><p class="note">EPS growth aur P/E assumptions ke examples, guaranteed targets ya price forecasts nahi.</p></div>
<div class="panel"><h3 class="section">Financial Details</h3><div class="tablewrap"><table><thead><tr><th>Financial year</th><th>Revenue</th><th>Net profit</th></tr></thead><tbody id="financials"></tbody></table></div></div>
<div class="panel"><h3 class="section">Investment se pehle verify karein</h3><ul class="items" id="warnings"></ul><p class="note">Data source: Yahoo Finance via yfinance. NSE/BSE filing aur financial statements final source maanein.</p></div></div><div class="foot">StockSahi India • Research tool only • No guaranteed returns • Data may be delayed or unavailable.</div></div>
<script>
var $=function(id){return document.getElementById(id)},selected="",last=null, timer=null;
function el(tag,text){var n=document.createElement(tag);n.textContent=text;return n}
function fmt(v,suffix){if(v===null||v===undefined||!isFinite(v))return "N/A";return Number(v).toLocaleString("en-IN",{maximumFractionDigits:2})+(suffix||"")}
function money(v){return v===null||v===undefined?"N/A":"₹"+fmt(v)}
function large(v){if(v===null||v===undefined)return "N/A";if(Math.abs(v)>=10000000)return "₹"+fmt(v/10000000)+" Cr";if(Math.abs(v)>=100000)return "₹"+fmt(v/100000)+" L";return money(v)}
function htmlClear(n){while(n.firstChild)n.removeChild(n.firstChild)}
function addList(id,items,empty){var e=$(id);htmlClear(e);(items.length?items:[empty]).forEach(function(t){e.appendChild(el("li",t))})}
async function lookup(q){if(q.length<2){$("suggest").style.display="none";return}try{var r=await fetch("/api/search?q="+encodeURIComponent(q));var data=await r.json();var box=$("suggest");htmlClear(box);(data.results||[]).forEach(function(x){var b=el("button",x.name+" ("+x.symbol+")");b.onclick=function(){selected=x.symbol;$("query").value=x.name;box.style.display="none";load(x.symbol)};box.appendChild(b)});box.style.display=box.children.length?"block":"none"}catch(e){$("suggest").style.display="none"}}
$("query").oninput=function(){selected="";clearTimeout(timer);var q=this.value;timer=setTimeout(function(){lookup(q)},330)}
var chips=["RELIANCE","TCS","INFOSYS","ITC","HDFC BANK","TATA STEEL","HAL"];
chips.forEach(function(name){var b=el("button",name);b.onclick=function(){$("query").value=name;load(name)};$("chips").appendChild(b)})
$("form").onsubmit=function(e){e.preventDefault();$("suggest").style.display="none";load(selected||$("query").value)}
function chart(points){var svg=$("chart");htmlClear(svg);if(!points||points.length<2){svg.appendChild(el("text","Price history unavailable"));return}var vals=points.map(function(x){return x.close}),lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),span=hi-lo||1;var p=points.map(function(x,i){return (20+i*460/(points.length-1)).toFixed(1)+","+(180-(x.close-lo)/span*145).toFixed(1)}).join(" ");var line=document.createElementNS("http://www.w3.org/2000/svg","polyline");line.setAttribute("points",p);line.setAttribute("fill","none");line.setAttribute("stroke","#36e3a1");line.setAttribute("stroke-width","3");svg.appendChild(line);var t=document.createElementNS("http://www.w3.org/2000/svg","text");t.setAttribute("x","12");t.setAttribute("y","20");t.setAttribute("fill","#b4cbd0");t.textContent="High "+money(hi)+" • Low "+money(lo);svg.appendChild(t)}
function render(d){last=d;$("result").style.display="block";$("symbol").textContent=d.symbol;$("company").textContent=d.company;$("sector").textContent=[d.sector,d.industry].filter(Boolean).join(" • ");$("price").textContent=money(d.price);$("asof").textContent="Latest chart date: "+(d.quote_as_of||"Not available")+" • Checked: "+new Date(d.checked_at).toLocaleString("en-IN");$("score").style.setProperty("--val",d.score||0);$("scoretxt").textContent=d.score===null?"N/A":d.score+"/100";$("signal").className="signal "+d.signal;$("signal").textContent=({CONSIDER:"CONSIDER BUY • Research First",WAIT:"WAIT • Rukkar check karein",AVOID:"AVOID • High risk",INCOMPLETE:"INCOMPLETE DATA",SPECIAL:"SPECIALIST REVIEW"})[d.signal]||d.signal;$("reason").textContent=d.reason;$("coverage").textContent="Available metric coverage: "+d.coverage+"%";
var labels={"sales_cagr":["Sales CAGR","%"],"profit_cagr":["Profit CAGR","%"],"latest_revenue_growth":["Recent Sales Growth","%"],"roe":["ROE","%"],"roce":["ROCE","%"],"operating_margin":["Operating Margin","%"],"debt_equity":["Debt / Equity",""],"operating_cash_flow":["Operating Cash Flow","large"],"free_cash_flow":["Free Cash Flow","large"],"pe":["P/E Ratio",""],"pb":["P/B Ratio",""],"eps":["EPS","₹"],"market_cap":["Market Cap","large"],"dividend_yield":["Dividend Yield","%"]};htmlClear($("metrics"));Object.keys(labels).forEach(function(key){var c=el("div","");c.className="metric";c.appendChild(el("small",labels[key][0]));var v=d.metrics[key],f=labels[key][1];c.appendChild(el("b",f==="large"?large(v):f==="₹"?money(v):fmt(v,f)));$("metrics").appendChild(c)});
htmlClear($("bars"));d.categories.forEach(function(c){var r=el("div","");r.className="barrow";r.appendChild(el("span",c.name));var bar=el("div","");bar.className="bar";var fill=el("i","");fill.style.width=(c.score||0)+"%";bar.appendChild(fill);r.appendChild(bar);r.appendChild(el("span",c.score===null?"N/A":c.score));$("bars").appendChild(r)});
chart(d.history);addList("positive",d.positives,"No strong positives identified in available data.");addList("risks",d.risks,"No flagged risks in available metrics. Still check corporate filings.");addList("warnings",d.warnings,"Please verify official filings.");htmlClear($("scenarios"));(d.scenarios.length?d.scenarios:[{name:"Not enough data",price:null,return_pct:null}]).forEach(function(s){var c=el("div","");c.appendChild(el("small",s.name));c.appendChild(el("strong",money(s.price)));c.appendChild(el("div",s.return_pct===null?"N/A":fmt(s.return_pct,"%")+" total 3-year illustrative return"));$("scenarios").appendChild(c)});htmlClear($("financials"));d.financials.forEach(function(f){var tr=el("tr","");[f.period,large(f.sales),large(f.profit)].forEach(function(x){tr.appendChild(el("td",x))});$("financials").appendChild(tr)});$("result").scrollIntoView({behavior:"smooth",block:"start"})}
async function load(q){q=q.trim();if(!q)return;var sym=COMMON_JS(q);$("status").textContent="Financial data load ho raha hai...";$("result").style.display="none";try{var r=await fetch("/api/report?symbol="+encodeURIComponent(sym));var data=await r.json();if(!r.ok)throw Error(data.error||"Data nahi mila");$("status").textContent="";render(data);history.replaceState(null,"","?symbol="+encodeURIComponent(data.symbol))}catch(e){$("status").textContent=e.message}}
function COMMON_JS(q){var map={"RELIANCE":"RELIANCE.NS","TCS":"TCS.NS","INFOSYS":"INFY.NS","ITC":"ITC.NS","HDFC BANK":"HDFCBANK.NS","ICICI BANK":"ICICIBANK.NS","SBI":"SBIN.NS","TATA MOTORS":"TATAMOTORS.NS","TATA STEEL":"TATASTEEL.NS","HAL":"HAL.NS","BEL":"BEL.NS","BHARTI AIRTEL":"BHARTIARTL.NS"};return map[q.toUpperCase()]||q.toUpperCase()}
function shareReport(){if(!last)return;var url=location.href;if(navigator.share){navigator.share({title:last.company+" - StockSahi Research",url:url}).catch(function(){})}else{navigator.clipboard.writeText(url).then(function(){alert("Report link copied")}).catch(function(){prompt("Copy URL",url)})}}
(function(){var q=new URLSearchParams(location.search).get("symbol");if(q){$("query").value=q;load(q)}})();
</script></body></html>"""
if __name__=="__main__":app.run(host="0.0.0.0",port=5000)
