'use strict';
const byId = id => document.getElementById(id);
const form = byId('search-form');
const searchInput = byId('search-input');
const suggestions = byId('suggestions');
const reportEl = byId('report');
const statusEl = byId('status');
const loadingEl = byId('loading');
let debounce, lastSuggestions = [], currentReport = null, requestId = 0;

const esc = str => String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isNum = x => typeof x === 'number' && Number.isFinite(x);
const nfmt = (v, decimals=1) => isNum(v) ? v.toLocaleString('en-IN',{minimumFractionDigits:decimals, maximumFractionDigits:decimals}) : 'N/A';
const cur = report => report.currency === 'INR' ? '₹' : ((report.currency || 'USD') === 'USD' ? '$' : esc(report.currency)+' ');
const priceFmt = (v, r) => isNum(v) ? `${cur(r)}${nfmt(v,2)}` : 'N/A';
const bigMoney = (v,r) => !isNum(v) ? 'N/A' : (r.currency === 'INR' ? `${cur(r)}${nfmt(v/1e7,1)} Cr` : `${cur(r)}${nfmt(v/1e6,1)} M`);
const metric = (label, value, hint='') => `<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value ${value==='N/A'?'na':''}">${esc(value)}</div><div class="metric-hint">${esc(hint)}</div></div>`;
const valPct = v => isNum(v) ? `${nfmt(v,1)}%` : 'N/A';
const signed = v => isNum(v) ? `${v > 0 ? '+' : ''}${nfmt(v,1)}%` : 'N/A';

function showStatus(message) {
  statusEl.textContent = message;
  statusEl.hidden = false;
}
function clearStatus() { statusEl.hidden = true; statusEl.textContent = ''; }
function setBusy(busy) {
  loadingEl.hidden = !busy;
  form.querySelector('button[type="submit"]').disabled = busy;
  if(busy){clearStatus();reportEl.hidden=true;suggestions.hidden=true;}
}
async function getJSON(path) {
  const controller = new AbortController();
  if (!navigator.onLine) throw new Error("Internet connection nahi hai. Financial report ke liye online hona zaroori hai.");
  const timeout = setTimeout(()=>controller.abort(), 90000);
  try {
    const res = await fetch(path, {signal: controller.signal, headers: {'Accept':'application/json'}});
    const json = await res.json();
    if(!res.ok) throw new Error(json.error || `Server error ${res.status}`);
    return json;
  } catch(e){
    if(e.name==='AbortError') throw new Error('Request timeout ho gaya. Dubara try karein.');
    throw e;
  } finally {clearTimeout(timeout);}
}
function makeSuggestions(stocks) {
  lastSuggestions=stocks;
  if(!stocks.length){suggestions.hidden=true;return;}
  suggestions.innerHTML=stocks.map((r,i)=>`<button type="button" role="option" data-index="${i}"><span><strong>${esc(r.name)}</strong><small>${esc(r.exchange||'Exchange not listed')}</small></span><span class="ticker">${esc(r.symbol)}</span></button>`).join('');
  suggestions.hidden=false;
}
suggestions.addEventListener('click',e=>{
  const btn=e.target.closest('button[data-index]');
  if(!btn)return;
  const selected=lastSuggestions[Number(btn.dataset.index)];
  if(selected)loadReport(selected.symbol);
});
searchInput.addEventListener('input',()=>{
  clearTimeout(debounce);
  const q=searchInput.value.trim();
  if(q.length<2){makeSuggestions([]);return;}
  debounce=setTimeout(async()=>{
    try {
      const result=await getJSON('/api/search?q='+encodeURIComponent(q));
      if(q!==searchInput.value.trim())return;
      makeSuggestions(result.results||[]);
    } catch(e){makeSuggestions([]);}
  },500);
});
document.addEventListener('click',e=>{
  if(!e.target.closest('.search-wrap'))suggestions.hidden=true;
});
form.addEventListener('submit', async e=>{
  e.preventDefault();
  const query=searchInput.value.trim();
  if(!query)return;
  if(/^[A-Za-z0-9.\-^=]+\.(NS|BO)$/i.test(query)){loadReport(query.toUpperCase());return;}
  if(lastSuggestions.length && lastSuggestions.some(r=>r.symbol.toUpperCase()===query.toUpperCase())){
    loadReport(query.toUpperCase());return;
  }
  try{
    clearStatus();
    const results=(await getJSON('/api/search?q='+encodeURIComponent(query))).results||[];
    if(results.length===1){loadReport(results[0].symbol);return;}
    const same=results.find(r=>r.name.toUpperCase()===query.toUpperCase() || r.symbol.toUpperCase()===query.toUpperCase()+'.NS');
    if(same){loadReport(same.symbol);return;}
    if(results.length>1){makeSuggestions(results);showStatus('Multiple companies milin. Niche search list mein sahi company select karein.');return;}
    if(/^[A-Za-z0-9-]{2,20}$/i.test(query)){loadReport(query.toUpperCase()+'.NS');return;}
    showStatus('Company nahi mili. Kripya exact NSE symbol likhein, jaise RELIANCE.NS ya TCS.NS.');
  }catch(e){showStatus(e.message);}
});
document.querySelectorAll('.popular [data-symbol]').forEach(el=>el.addEventListener('click',()=>loadReport(el.dataset.symbol)));

async function loadReport(symbol){
  const current=++requestId;
  searchInput.value=symbol;
  setBusy(true);
  try {
    const data=await getJSON('/api/report?symbol='+encodeURIComponent(symbol));
    if(current!==requestId)return;
    currentReport=data;
    renderReport(data);
    reportEl.hidden=false;
    reportEl.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){if(current===requestId)showStatus(e.message);}finally{if(current===requestId)setBusy(false);}
}
const list = (arr,type) => arr && arr.length ? `<ul class="notes-list ${type||''}">${arr.map(x=>`<li><i>${type==='negative'?'!':type==='neutral'?'i':'✓'}</i><span>${esc(x)}</span></li>`).join('')}</ul>` : `<div class="empty-state">Is category ke liye sufficient verified numbers nahi mile.</div>`;
async function renderPeers(r, target) {
  try {
    const data = await getJSON('/api/peers?symbol=' + encodeURIComponent(r.symbol));
    if (!data.industry) {
      target.textContent = 'Is stock ke liye peer group available nahi hai. Valuation verify karne ke baad hi entry consider karein.';
      return;
    }
    const formats = [
      ['trailing_pe','P/E',v=>nfmt(v,1)+'x'],
      ['price_to_book','P/B',v=>nfmt(v,1)+'x'],
      ['revenue_cagr','Sales CAGR',valPct], ['profit_cagr','Profit CAGR',valPct],
      ['roe','ROE',valPct], ['roce','ROCE',valPct],
      ['operating_margin','Operating margin',valPct],
      ['debt_equity','Debt / Equity',v=>nfmt(v,2)],
      ['current_ratio','Current ratio',v=>nfmt(v,2)],
      ['eps','EPS (TTM)',v=>priceFmt(v,r)],
      ['operating_cash_flow','Operating cash flow',v=>bigMoney(v,r)],
      ['free_cash_flow','Free cash flow',v=>bigMoney(v,r)]
    ];
    const rows = formats.map(([key,label,format])=>{
      const benchmark = data.benchmarks[key], actual = r.metrics[key];
      return '<tr><td>'+esc(label)+'</td><td>'+esc(isNum(actual)?format(actual):'N/A')+'</td><td>'+
        esc(benchmark?format(benchmark.median):'N/A')+'</td><td>'+
        (benchmark?Object.entries(benchmark.values).map(([peer,value])=>esc(peer+' '+format(value))).join(' · '):'')+'</td></tr>';
    }).join('');
    const bank = data.industry.includes('banks');
    const key = bank?'price_to_book':'trailing_pe';
    const label = bank?'P/B':'P/E';
    const benchmark = data.benchmarks[key]?.median, actual = r.metrics[key];
    let conclusion = 'Wait for data. Comparable '+label+' verify karein.';
    if (isNum(actual) && actual > 0 && benchmark > 0) {
      const gap = (actual/benchmark-1)*100;
      if (gap > 15) conclusion = label+' peers se '+nfmt(gap,1)+'% premium par hai. Wait karein aur dekhein kya growth ya profitability premium justify karti hai.';
      else if (gap < -15) conclusion = label+' peers se '+nfmt(-gap,1)+'% discount par hai. Discount ka reason, earnings quality aur risks verify karein.';
      else conclusion = label+' peer median ke kareeb hai. Entry decide karne se pehle latest results aur growth check karein.';
      if (r.score.signal === 'AVOID') conclusion += ' Financial risk flags ke chalte abhi entry avoid karein.';
      else if (r.score.signal === 'CONSIDER' && gap <= 15) conclusion += ' Fundamentals screening pass hai, further research ke liye shortlist kar sakte hain.';
      if (bank) conclusion += ' Bank ke NPA, NIM aur capital adequacy bhi check karein.';
    }
    target.innerHTML = '<p><strong>'+esc(data.industry)+'</strong> · '+esc(data.peers.join(', '))+'</p>'+
      '<div style="overflow-x:auto"><table><thead><tr><th>Metric</th><th>Company</th><th>Peer median</th><th>Peer values</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
      '<p><strong>Research conclusion</strong> '+esc(conclusion)+'</p>'+
      '<p class="section-sub">Yahoo Finance data. Har metric ke liye kam se kam 2 peer values chahiye. Median selected peers ka hai. EPS aur cash flow company size se affect hote hain. Relative premium ya discount fair value estimate nahi hai.</p>';
  } catch {
    target.textContent = 'Peer data abhi load nahi hua. Valuation compare karne ke liye baad mein report dobara kholein.';
  }
}
function tradingVolume(rows) {
  const latest = rows?.at(-1);
  if (!latest || !isNum(latest.shares)) return 'Trading volume available nahi hai.';
  const previous = rows.slice(0, -1);
  const average = previous.length === 20 && previous.every(row => isNum(row.shares))
    ? previous.reduce((sum, row) => sum + row.shares, 0) / 20 : null;
  return '<p>' + esc(latest.date) + ' · <strong>' + nfmt(latest.shares, 0) +
    ' shares traded</strong></p><p>Previous 20-session average ' +
    (average > 0 ? nfmt(average, 0) + ' shares · ' + nfmt(latest.shares / average, 2) + '× average' : 'N/A') +
    '</p><p class="section-sub">Yahoo Finance daily volume. Latest session may be partial or delayed.</p>';
}

let activeDealType = 'bulk';
let dealRequest;
let visibleDeals = [];
const dealFields = [["date","Date"],["symbol","Symbol"],["name","Security name"],["clientName","Client name"],["buySell","Buy/Sell"],["qty","Volume"],["watp","Trade price / weighted average (₹)"],["remarks","Remarks"]];

async function showNseDeals() {
  const host = byId('nse-deals-results');
  host.textContent = 'NSE data load ho raha hai…';
  byId('nse-deals-download').disabled = true;
  try {
    dealRequest ||= getJSON('/api/nse-deals').catch(error => {
      dealRequest = null;
      throw error;
    });
    const snapshot = await dealRequest;
    const term = byId('nse-deal-search').value.trim().toUpperCase();
    const rows = snapshot[activeDealType];
    visibleDeals = rows.filter(row => !term ||
      [row.symbol, row.name, row.clientName].some(value => String(value || '').toUpperCase().includes(term)));
    byId('nse-deals-download').disabled = !visibleDeals.length;
    host.innerHTML = '<p><strong>' + visibleDeals.length + ' of ' + rows.length + ' records</strong> · ' +
      esc(snapshot.date) + (snapshot.saved ? ' · Saved NSE snapshot' : ' · NSE feed') + '</p>' +
      (visibleDeals.length ? '<div style="overflow-x:auto"><table><thead><tr>' +
        dealFields.map(([,label]) => '<th scope="col">' + esc(label) + '</th>').join('') +
        '</tr></thead><tbody>' + visibleDeals.map(row => '<tr>' + dealFields.map(([key]) =>
          '<td>' + esc(row[key] ?? 'N/A') + '</td>').join('') + '</tr>').join('') +
        '</tbody></table></div>' : '<p>Is snapshot mein matching record nahi mila.</p>');
  } catch (error) {
    host.textContent = error.message;
  }
}

const dealSection = byId('nse-deals');
dealSection.querySelectorAll('[data-deal-type]').forEach(button => {
  button.addEventListener('click', () => {
    activeDealType = button.dataset.dealType;
    dealSection.querySelectorAll('[data-deal-type]').forEach(item =>
      item.setAttribute('aria-pressed', String(item === button)));
    showNseDeals();
  });
});
byId('nse-deal-search').addEventListener('input', showNseDeals);
byId('nse-deals-download').addEventListener('click', () => {
  const quote = value => {
    const cell = String(value ?? '');
    return '"' + (/^[\s]*[=+@-]/.test(cell) && cell !== '-' ? "'" : '') + cell.replaceAll('"', '""') + '"';
  };
  const lines = [dealFields.map(([,label]) => quote(label)).join(','),
    ...visibleDeals.map(row => dealFields.map(([key]) => quote(row[key])).join(','))];
  const url = URL.createObjectURL(new Blob(['\uFEFF' + lines.join('\r\n')], {type:'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'nse-' + activeDealType + '-deals.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
dealSection.addEventListener('toggle', () => {
  if (dealSection.open) {
    dealRequest = null;
    showNseDeals();
  }
});

function renderReport(r){
  const s=r.score,m=r.metrics,good=s.signal==='CONSIDER',bad=s.signal==='AVOID';
  const color=good?'#58d5aa':bad?'#ff9098':s.signal==='WAIT'?'#f5c47d':'#9cb0c3';
  const ring=isNum(s.total)?s.total:0;
  const tabs=`<div class="chart-tabs"><button class="active" data-years="1">1Y</button><button data-years="3">3Y</button><button data-years="5">5Y</button></div>`;
  const metrics=[
    ['Sales CAGR', valPct(m.revenue_cagr),'Annual sales trend'],
    ['Profit CAGR',valPct(m.profit_cagr),'Annual profit trend'],
    ['ROE',valPct(m.roe),'Shareholder returns'],
    ['ROCE',valPct(m.roce),'Capital efficiency'],
    ['Debt / Equity',nfmt(m.debt_equity,2),'Lower generally better'],
    ['Operating margin',valPct(m.operating_margin),'Business profitability'],
    ['P/E Ratio',nfmt(m.trailing_pe,1)+'x','Price / earnings'],
    ['EPS (TTM)',priceFmt(m.eps,r),'Earnings / share'],
    ['P/B Ratio',nfmt(m.price_to_book,1)+'x','Price / book'],
    ['Operating cash flow',bigMoney(m.operating_cash_flow,r),'Latest annual'],
    ['Free cash flow',bigMoney(m.free_cash_flow,r),'Latest annual'],
    ['Current Ratio',nfmt(m.current_ratio,2),'Short-term liquidity'],
  ];
  // Ensure unavailable P/E and P/B show N/A instead of N/Ax.
  metrics[6][1]=isNum(m.trailing_pe)?nfmt(m.trailing_pe,1)+'x':'N/A';
  metrics[8][1]=isNum(m.price_to_book)?nfmt(m.price_to_book,1)+'x':'N/A';
  const annual=[...(r.annual||[])].reverse();
  const q=[...(r.quarterly||[])];
  reportEl.innerHTML=`
  <div class="report-top"><div><div class="report-kicker">FUNDAMENTAL RESEARCH REPORT</div><h2 class="report-name">${esc(r.name)}</h2><div class="report-sub">${esc(r.symbol)} · ${esc(r.exchange)} · ${esc(r.sector)} · ${esc(r.industry)}</div></div><div class="report-actions"><button id="print-report">↧ &nbsp; Save as PDF</button><button id="share-report">↗ &nbsp; Share</button><button id="new-search">⌕ &nbsp; New search</button></div></div>
  <div class="report-main">
    <article class="report-card verdict-card"><div class="score-circle" style="background:conic-gradient(${color} ${ring}%,#304658 ${ring}%);"><div class="score-inner"><strong>${isNum(s.total)?s.total:'--'}</strong><span>out of 100</span></div></div><div class="verdict-copy"><span class="verdict-label ${s.signal.toLowerCase()}">${esc(s.signal==='CONSIDER'?'CONSIDER BUY':s.signal==='WAIT'?'WAIT':s.signal==='AVOID'?'AVOID':'NEEDS REVIEW')}</span><h3>${esc(s.signal_hi)}</h3><p>${esc(s.summary)}</p><div class="verdict-foot">Data coverage: ${s.coverage}% · Confidence: ${esc(s.confidence)}</div></div></article>
    <article class="report-card quote-card"><div><div class="quote-head"><span class="tiny-label">LATEST AVAILABLE CLOSE</span><span class="exchange-chip">${esc(r.exchange||'SHARE')}</span></div><div class="quote-price">${priceFmt(r.price,r)}</div><div class="quote-date">${esc(r.quote_date)} · price may be delayed</div></div><div class="quote-bottom"><div><small>1-year price change</small><strong class="${(r.one_year_return||0)<0?'down':'up'}">${signed(r.one_year_return)}</strong></div><div><small>Market cap</small><strong>${bigMoney(m.market_cap,r)}</strong></div></div></article>
  </div>
  <article class="report-card chart-card"><h3>Industry peer comparison</h3><div id="peer-comparison">Peer numbers load ho rahe hain...</div></article>
  <div class="report-grid">
    <article class="report-card"><h3>Financial health score</h3><div class="section-sub">Rules-based weightage, 100-point scale</div>${s.categories.map(c=>`<div class="score-row"><label>${esc(c.label)}</label><div class="bar-track"><div class="bar-fill" style="width:${isNum(c.score)?c.score:0}%"></div></div><div class="score-value">${isNum(c.score)?Math.round(c.score):'N/A'}</div></div>`).join('')}<div class="chart-footer">Note: Missing metric score mein zero nahi lagaya. Available groups ke basis par weight adjust hota hai.</div></article>
    <article class="report-card"><h3>Key financial ratios</h3><div class="section-sub">Actual available financial values</div><div class="metric-grid">${metrics.map(x=>metric(...x)).join('')}</div></article>
  </div>
  <article class="report-card chart-card"><h3>Trading volume</h3>${tradingVolume(r.daily_volume)}</article>
  <article class="report-card chart-card"><div class="chart-top"><div><h3>Share price history</h3><div class="section-sub">Past closing prices · adjusted for neither dividends nor total return</div></div>${tabs}</div><div class="chart-container" id="price-chart"></div><div class="chart-footer">Historical price chart sirf context ke liye hai, future growth ki guarantee nahi.</div></article>
  <div class="report-grid">
    <article class="report-card"><h3>✓ Achhe points</h3><div class="section-sub">Available data mein positive signals</div>${list(r.positive)}</article>
    <article class="report-card"><h3>! Risk aur weak points</h3><div class="section-sub">Invest karne se pehle check karein</div>${list(r.concerns,'negative')}</article>
  </div>
  <article class="report-card chart-card"><h3>Annual financial history</h3><div class="section-sub">Reported fiscal years · values in ${r.currency==='INR'?'₹ crore':esc(r.currency)+' million'} · figures may be restated</div>${financialTable(annual,r)}${q.length?`<h3 style="margin-top:28px">Recent quarterly results</h3><div class="section-sub">Quarter-end data (as available)</div>${financialTable(q,r,true)}`:''}</article>
  <article class="report-card chart-card"><h3>3-year scenario analysis</h3><div class="section-sub">Profit/EPS growth aur future P/E badalne par price kya ho sakta hai?</div>${r.scenarios?.length?`<div class="scenario-grid">${r.scenarios.map(sc=>`<div class="scenario"><div class="scenario-title">${esc(sc.name)}</div><div class="scenario-price">${priceFmt(sc.price,r)}</div><div class="scenario-change ${sc.change_pct<0?'down':'up'}">${signed(sc.change_pct)} vs today</div><div class="scenario-assumption">Assumed EPS growth: <b>${signed(sc.eps_growth)} yearly</b><br>Assumed P/E after 3Y: <b>${nfmt(sc.future_pe,1)}x</b></div></div>`).join('')}</div>`:`<div class="empty-state">EPS / valuation / financial history poora nahi mila, isliye speculative price calculation nahi dikhaya.</div>`}<div class="scenario-warning">⚠ ${esc(r.scenario_note)}</div></article>
  <article class="report-card chart-card"><h3>Verify before investing</h3><div class="section-sub">Jo cheezein automated ratio analysis se confirm nahi hotin</div>${list(r.cautions,'neutral')}</article>
  <article class="report-card chart-card"><h3>Data source & calculation</h3><p style="font-size:12px;color:#718696;line-height:1.8">${esc(r.methodology)}<br>Report generated: ${esc(new Date(r.fetched_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}))} IST. Delayed price, incomplete statements, restatements aur sector differences ho sakte hain.</p><div class="sources"><a href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">Yahoo Finance source ↗</a><a href="https://www.nseindia.com/companies-listing/corporate-filings-financial-results" target="_blank" rel="noopener noreferrer">NSE official financial filings ↗</a><a href="https://www.bseindia.com/" target="_blank" rel="noopener noreferrer">BSE official filings ↗</a></div></article>
  `;
  renderPeers(r, byId('peer-comparison'));
  byId('print-report').addEventListener('click',()=>window.print());
  byId('share-report').addEventListener('click',async()=>{
    const url=new URL(window.location.href);url.searchParams.set('symbol',r.symbol);
    try{
      if(navigator.share) await navigator.share({title:`StockSahi: ${r.name}`,text:'Company fundamentals report (verify original filings)',url:url.toString()});
      else if(navigator.clipboard){await navigator.clipboard.writeText(url.toString());byId('share-report').textContent='✓ Link copied';}
      else window.prompt('Copy this report link:',url.toString());
    }catch(e){if(e.name!=='AbortError')showStatus('Share nahi ho saka. Link copy karke try karein.');}
  });
  byId('new-search').addEventListener('click',()=>{window.scrollTo({top:0,behavior:'smooth'});searchInput.focus();searchInput.select()});
  reportEl.querySelectorAll('.chart-tabs button').forEach(el=>el.addEventListener('click',()=>{
    reportEl.querySelectorAll('.chart-tabs button').forEach(b=>b.classList.toggle('active',b===el));
    renderPriceChart(r.price_history||[],Number(el.dataset.years),r);
  }));
  renderPriceChart(r.price_history||[],1,r);
}
function financialTable(rows,r,quarterly=false){
  if(!rows.length)return `<div class="empty-state">Financial statements ka data available nahi hai.</div>`;
  const capital=quarterly?'<th>Period end</th>':'<th>FY end</th>';
  return `<div class="table-wrap"><table class="financial-table"><thead><tr>${capital}<th>Revenue</th><th>Net Profit</th><th>EBIT</th>${quarterly?'':'<th>Operating CF</th><th>Free CF</th>'}</tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.period_end || x.year)}</td><td>${bigMoney(x.revenue,r)}</td><td>${bigMoney(x.profit,r)}</td><td>${bigMoney(x.ebit,r)}</td>${quarterly?'':`<td>${bigMoney(x.cfo,r)}</td><td>${bigMoney(x.fcf,r)}</td>`}</tr>`).join('')}</tbody></table></div>`;
}
function renderPriceChart(history,years,r){
  const host=byId('price-chart');if(!host)return;
  if(!history.length){host.innerHTML='<div class="empty-state">Price chart available nahi hai.</div>';return;}
  const last=new Date(history[history.length-1].date+'T12:00:00Z');
  const cutoff=new Date(last);cutoff.setUTCFullYear(cutoff.getUTCFullYear()-years);
  const items=history.filter(i=>new Date(i.date+'T12:00:00Z')>=cutoff && isNum(i.close));
  if(items.length<2){host.innerHTML='<div class="empty-state">Is duration ka sufficient data nahi mila.</div>';return;}
  const values=items.map(p=>p.close);
  let min=Math.min(...values),max=Math.max(...values); const extent=Math.max(max-min,max*.03,1);
  min=Math.max(0,min-extent*.18);max+=extent*.18;
  const W=850,H=264,L=55,R=22,T=18,B=35,w=W-L-R,h=H-T-B;
  const point=(i,v)=>[(L+(i/(items.length-1))*w).toFixed(1),(T+(1-(v-min)/(max-min))*h).toFixed(1)];
  const coordinates=items.map((p,i)=>point(i,p.close));
  const path=coordinates.map((p,i)=>`${i===0?'M':'L'}${p.join(' ')}`).join(' ');
  const grid=Array.from({length:5},(_,i)=>{
    const y=T+i*h/4, v=max-i*(max-min)/4;
    return `<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#e5ecf0" stroke-dasharray="4 5"/><text x="${L-8}" y="${y+4}" text-anchor="end" font-size="10" fill="#8498a6">${esc(nfmt(v,0))}</text>`;
  }).join('');
  const start=items[0].date, mid=items[Math.floor(items.length/2)].date, end=items[items.length-1].date;
  const axis=[{x:L,text:start},{x:L+w/2,text:mid},{x:W-R,text:end}].map(a=>`<text x="${a.x}" y="${H-6}" text-anchor="${a.x===L?'start':a.x===W-R?'end':'middle'}" fill="#8398a5" font-size="11">${esc(a.text)}</text>`).join('');
  host.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${years} year historical share price chart"><defs><linearGradient id="area-${years}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#51cca0" stop-opacity=".21"/><stop offset="1" stop-color="#51cca0" stop-opacity="0"/></linearGradient></defs>${grid}<path d="${path} L${L+w} ${T+h} L${L} ${T+h}Z" fill="url(#area-${years})"/><path d="${path}" fill="none" stroke="#2cab82" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${coordinates.at(-1)[0]}" cy="${coordinates.at(-1)[1]}" r="4.4" fill="#2cab82" stroke="#fff" stroke-width="2"/>${axis}</svg>`;
}
const param=new URLSearchParams(window.location.search).get('symbol');
if(param && /^[A-Za-z0-9.\-^=]{1,30}$/.test(param)) loadReport(param);

// PWA installation requires HTTPS hosting. Cached pages do not include live report data.
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  window.addEventListener('load',()=>navigator.serviceWorker.register('/static/sw.js').catch(()=>{}));
}
const off=byId('offline-note');
if (off) {off.hidden=navigator.onLine;window.addEventListener('offline',()=>{off.hidden=false});window.addEventListener('online',()=>{off.hidden=true});}

async function showMarket() {
  const strip = byId('market-indices');
  const detail = byId('market-detail');
  try {
    const indices = await getJSON('/api/market-overview');
    let selected = indices.findIndex(index => index.points.length >= 2);
    let range = 22;
    const change = index => {
      const last = index.points.at(-1).close;
      const prior = index.points.at(-2).close;
      return {last, amount:last-prior, percent:(last/prior-1)*100};
    };
    const render = () => {
      strip.innerHTML = indices.map((index,i) => {
        const ready = index.points.length >= 2;
        const quote = ready ? change(index) : null;
        return '<button class="index-card '+(quote && quote.amount < 0?'negative':'')+
          '" data-index="'+i+'" aria-pressed="'+(i===selected)+'" '+(ready?'':'disabled')+'>'+
          '<span>'+esc(index.name)+'</span><strong>'+(quote?nfmt(quote.last,2):'N/A')+'</strong>'+
          '<small>'+(quote?signed(quote.percent):'Data unavailable')+'</small></button>';
      }).join('');
      if (selected < 0) {
        detail.textContent = 'Index data abhi available nahi hai. Thodi der baad refresh karein.';
        return;
      }
      const index = indices[selected];
      const quote = change(index);
      const points = index.points.slice(-range);
      const values = points.map(point => point.close);
      const min = Math.min(...values), max = Math.max(...values);
      const coords = points.map((point,i) => [60+ i*820/(points.length-1), 220-(point.close-min)*185/(max-min||1)].map(n=>n.toFixed(2)).join(','));
      const grid = [0,1,2,3,4].map(i => {
        const y = 35+i*185/4;
        return '<line x1="60" x2="880" y1="'+y+'" y2="'+y+'" stroke="#e1e4ef"/>'+
          '<text x="2" y="'+(y+4)+'">'+nfmt(max-(max-min)*i/4,0)+'</text>';
      }).join('');
      detail.innerHTML = '<div class="market-quote"><div><h2>'+esc(index.name)+'</h2><strong>'+nfmt(quote.last,2)+'</strong><p class="'+(quote.amount<0?'down':'up')+'">'+
        (quote.amount>0?'+':'')+nfmt(quote.amount,2)+' ('+signed(quote.percent)+')</p></div>'+
        [['Open',index.open],['High',index.high],['Low',index.low]].map(([label,v])=>'<div><span>'+label+'</span><strong>'+nfmt(v,2)+'</strong></div>').join('')+'</div>'+
        '<div class="market-chart-bar"><span>Latest session '+esc(points.at(-1).date)+'</span><div class="market-ranges">'+
        [[22,'1M'],[66,'3M'],[132,'6M'],[260,'1Y']].map(([n,label])=>'<button data-range="'+n+'" aria-pressed="'+(n===range)+'">'+label+'</button>').join('')+'</div></div>'+
        '<svg class="market-chart" viewBox="0 0 900 250" role="img" aria-label="'+esc(index.name)+' daily close history"><defs><linearGradient id="index-fill" x2="0" y2="1"><stop stop-color="#6ca9d2" stop-opacity=".65"/><stop offset="1" stop-color="#eaf6fc"/></linearGradient></defs>'+
        grid+'<polygon points="60,220 '+coords.join(' ')+' 880,220" fill="url(#index-fill)"/>'+
        '<polyline points="'+coords.join(' ')+'" fill="none" stroke="#413581" stroke-width="2" vector-effect="non-scaling-stroke"/>'+
        '<text x="60" y="244">'+esc(points[0].date)+'</text><text x="880" y="244" text-anchor="end">'+esc(points.at(-1).date)+'</text></svg>';
    };
    strip.addEventListener('click',event=>{
      const button = event.target.closest('[data-index]');
      if (button) {selected = Number(button.dataset.index);render();}
    });
    detail.addEventListener('click',event=>{
      const button = event.target.closest('[data-range]');
      if (button) {range = Number(button.dataset.range);render();}
    });
    render();
  } catch {
    detail.textContent = 'Index data abhi load nahi hua. Thodi der baad refresh karein.';
  }
}
showMarket();
document.querySelector('.market-nav a[href="#nse-deals"]').addEventListener('click',()=>{
  byId('nse-deals').open = true;
});
if (location.hash === '#nse-deals') byId('nse-deals').open = true;
