(() => {
  const timestamp = document.getElementById('market-stat-time');
  const source = document.querySelector('#market-statistics > p.market-source');
  if (!timestamp || !source) return;
  let busy = false;
  let lastUpdate = '';
  const format = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 2});
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const response = await fetch('/api/market-statistics', {cache:'no-store', signal:AbortSignal.timeout(12000)});
      if (!response.ok) throw new Error('NSE feed unavailable');
      const data = await response.json();
      if (!data.asOnDate || !data.snapshotCapitalMarket) throw new Error('Missing NSE data');
      const values = {...data.snapshotCapitalMarket, ...data.fiftyTwoWeek, ...data.circuit,
        accounts:data.regInvestors, cap: typeof data.tlMKtCapLacCr === 'number' ? '₹'+format.format(data.tlMKtCapLacCr)+' lakh crore' : null};
      document.querySelectorAll('[data-market-stat]').forEach(node => {
        const value = values[node.dataset.marketStat];
        node.textContent = typeof value === 'number' ? format.format(value) : value ?? '—';
      });
      lastUpdate = data.asOnDate;
      timestamp.textContent = 'NSE data · ' + lastUpdate + ' IST';
      source.firstChild.textContent = 'Source: NSE · ';
    } catch {
      timestamp.textContent = lastUpdate ? 'Last received · ' + lastUpdate + ' IST · Feed unavailable'
        : 'Saved snapshot · 13 Nov 2026, 4:00 PM IST · Feed unavailable';
    } finally {
      busy = false;
    }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', refresh);
})();
