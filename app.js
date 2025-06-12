// app.js
const API_URL = 'https://script.google.com/macros/s/AKfycbyvYoKMlljjaxR1fjFwFuZ7Dv9LS6Xva4NOE9dCDJr5_dIaaFyq2DXUsepvDqM2_qD3/exec';

async function fetchMatchesFromSource() {
  const pages = [
    { name: 'qualificationMatches', tag: 'Qual' },
    { name: 'finals',             tag: 'Final' }
  ];
  let matches = [];
  for (let {name, tag} of pages) {
    try {
      const resp = await fetch(`${API_URL}?page=${name}`);
      if (!resp.ok) throw new Error('Network error');
      const data = await resp.json();
      for (let row of data) {
        const team1 = row[1].split('|',1)[0].trim();
        const team2 = row[2].split('|',1)[0].trim();
        const s1 = /^\d+$/.test(row[3]) ? +row[3] : null;
        const s2 = /^\d+$/.test(row[4]) ? +row[4] : null;
        matches.push({team1,team2,s1,s2,tag});
      }
    } catch {
      // skip on error
    }
  }
  return matches;
}

function oprcalc(matches) {
  // collect teams
  const teams = Array.from(new Set(matches.flatMap(m=>[m.team1, m.team2]))).sort();
  if (!teams.length) return {};
  const idx = Object.fromEntries(teams.map((t,i)=>[t,i]));
  // build A and b
  let rows = [], b = [];
  for (let m of matches) {
    if (m.s1==null || m.s2==null) continue;
    let r = Array(teams.length).fill(0);
    r[idx[m.team1]] = 1; rows.push(r); b.push(m.s1);
    r = Array(teams.length).fill(0);
    r[idx[m.team2]] = 1; rows.push(r); b.push(m.s2);
  }
  if (!rows.length) return {};
  const A = math.matrix(rows);
  const bvec = math.matrix(b);
  // solve x = (A^T A)^-1 A^T b
  const At = math.transpose(A);
  const ATA = math.multiply(At, A);
  const ATb = math.multiply(At, bvec);
  const x = math.multiply(math.inv(ATA), ATb).toArray();
  let result = {};
  teams.forEach((t,i)=>result[t]=x[i]);
  return result;
}

async function buildIndexPage() {
  const all = await fetchMatchesFromSource();
  const played = all.filter(m => m.s1!=null && m.s2!=null);
  // compute rankings
  let oprs = oprcalc(played);
  oprs = Object.fromEntries(Object.entries(oprs).sort((a,b)=>b[1]-a[1]));
  let rp = {}, tbp = {}, mx = {};
  for (let t of Object.keys(oprs)) { rp[t]=0; tbp[t]=0; mx[t]=0; }
  for (let m of played) {
    tbp[m.team1] += m.s1;
    tbp[m.team2] += m.s2;
    if (m.s1>m.s2) rp[m.team1]+=2;
    else if (m.s2>m.s1) rp[m.team2]+=2;
    else { rp[m.team1]++; rp[m.team2]++; }
    mx[m.team1] = Math.max(mx[m.team1], m.s1);
    mx[m.team2] = Math.max(mx[m.team2], m.s2);
  }
  const worldHigh = Math.max(...Object.values(mx), 0);
  document.getElementById('world-high-value').textContent = worldHigh;

  // progression data
  const teams = Object.keys(oprs);
  const labels = played.map((_,i)=>i+1);
  const teamHist = {};
  teams.forEach(t=>teamHist[t]=[]);
  for (let i=1; i<=played.length; i++) {
    const histOpr = oprcalc(played.slice(0,i));
    teams.forEach(t=>teamHist[t].push(+histOpr[t]?.toFixed(2)||0));
  }

  // render rankings table
  const rankBody = document.getElementById('rankings-body');
  rankBody.innerHTML = '';
  Object.entries(oprs).forEach(([team, val], i) => {
    const tr = document.createElement('tr');
    if (i===0) tr.classList.add('top-team');
    tr.classList.add('team-row');
    tr.innerHTML = `
      <td>${i+1}</td>
      <td><a href="team.html?team=${team}" target="_blank">${team}</a></td>
      <td>${val.toFixed(2)}</td>
      <td>${rp[team]}</td>
      <td>${tbp[team]}</td>
      <td>${mx[team]}</td>
    `;
    rankBody.appendChild(tr);
  });

  // render match history table
  const histBody = document.getElementById('history-body');
  histBody.innerHTML = '';
  played.forEach((m,i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${i+1}</td>
      <td>${m.tag}</td>
      <td>${m.team1}</td>
      <td>${m.s1}</td>
      <td>${m.team2}</td>
      <td>${m.s2}</td>
    `;
    histBody.appendChild(tr);
  });

  // draw all-teams chart
  const datasets = Object.entries(teamHist).map(([team, data]) => {
    // random pastel
    const r = ()=>Math.floor(Math.random()*200);
    const color = `rgb(${r()},${r()},${r()})`;
    return {
      label: team,
      data,
      fill: false,
      tension: 0.2,
      borderColor: color,
      backgroundColor: color,
      borderWidth: 2,
      pointRadius: 3
    };
  });
  new Chart(document.getElementById('allChart'), {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { padding: 20, usePointStyle: true }},
        tooltip: { mode: 'index', intersect: false }
      },
      interaction: { mode: 'nearest', intersect: true },
      scales: {
        x: { title: { display: true, text: 'Match #' }, grid: { display: false } },
        y: { title: { display: true, text: 'OPR' }, grid: { color: '#f0f0f0' } }
      }
    }
  });
}

async function buildTeamPage() {
  const params = new URLSearchParams(window.location.search);
  const team = params.get('team') || '';
  document.getElementById('team-heading').textContent = `OPR Over Time: ${team}`;

  const all = await fetchMatchesFromSource();
  const played = all.filter(m => m.s1!=null && m.s2!=null);
  const history = [];
  for (let i=1; i<=played.length; i++) {
    const h = oprcalc(played.slice(0,i));
    history.push({ match_idx: i, opr: +(h[team]?.toFixed(2) || 0) });
  }

  const ctx = document.getElementById('teamChart');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: history.map(x=>x.match_idx),
      datasets: [{ 
        label: 'OPR',
        data: history.map(x=>x.opr),
        fill: false,
        tension: 0.2,
        borderColor: '#4a6cf7',
        backgroundColor: 'rgba(74,108,247,0.1)',
        borderWidth: 3,
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: items => `Match #${items[0].label}`,
            label: item => `OPR: ${item.raw}`
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'Match #' }, grid: { display: false }},
        y: { title: { display: true, text: 'OPR' }, grid: { color: '#f0f0f0' }}
      }
    }
  });
}
