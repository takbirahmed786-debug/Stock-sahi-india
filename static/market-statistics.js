(() => {
  const timestamp = document.getElementById('market-stat-time');
  const source = document.querySelector('#market-statistics > p.market-source');
  if (!timestamp || !source) return;
  let busy = false;
  const savedTimestamp = timestamp.textContent;
  let lastUpdate = '';
  const format = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 2});
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch('/api/market-statistics', {cache:'no-store', signal:controller.signal});
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
        : savedTimestamp + ' · Feed unavailable';
    } finally {
      clearTimeout(deadline);
      busy = false;
    }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', refresh);
})();
