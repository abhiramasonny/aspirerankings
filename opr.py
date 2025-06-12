from flask import Flask, request, jsonify, render_template_string
import requests
import numpy as np

app = Flask(__name__)

API_URL = "https://script.google.com/macros/s/AKfycbyvYoKMlljjaxR1fjFwFuZ7Dv9LS6Xva4NOE9dCDJr5_dIaaFyq2DXUsepvDqM2_qD3/exec"

def fetch_matches_from_source():
  """
  Fetch both qualification and finals matches, tag them,
  and skip any that fail to return valid JSON.
  """
  pages = [
    ("qualificationMatches", "Qual"),
    ("finals",             "Final")
  ]
  matches = []
  for page_name, tag in pages:
    try:
      resp = requests.get(f"{API_URL}?page={page_name}")
      resp.raise_for_status()
      data = resp.json()        # may raise ValueError if non-JSON
    except (requests.RequestException, ValueError):
      # skip this page if network error or not JSON
      continue

    for row in data:
      team1 = row[1].split("|",1)[0].strip()
      team2 = row[2].split("|",1)[0].strip()
      s1 = int(row[3]) if str(row[3]).isdigit() else None
      s2 = int(row[4]) if str(row[4]).isdigit() else None
      matches.append((team1, team2, s1, s2, tag))

  return matches

def oprcalc(matches):
  teams = sorted({t for m in matches for t in m[:2]})
  if not teams:
    return {}
  idx = {t:i for i,t in enumerate(teams)}
  rows, b = [], []
  for t1, t2, s1, s2, *_ in matches:
    if s1 is None or s2 is None:
      continue
    r = np.zeros(len(teams)); r[idx[t1]] = 1
    rows.append(r); b.append(s1)
    r = np.zeros(len(teams)); r[idx[t2]] = 1
    rows.append(r); b.append(s2)
  if not rows:
    return {}
  A = np.vstack(rows); b = np.array(b)
  x, *_ = np.linalg.lstsq(A, b, rcond=None)
  return {team: float(x[idx[team]]) for team in teams}

@app.route("/")
def index():
  all_matches = fetch_matches_from_source()

  # only fully played
  played = [(a,b,sa,sb,typ) for a,b,sa,sb,typ in all_matches if sa is not None and sb is not None]

  # compute final rankings
  oprs = oprcalc(played)
  oprs = dict(sorted(oprs.items(), key=lambda kv: kv[1], reverse=True))
  rp  = {t:0 for t in oprs}
  tbp = {t:0 for t in oprs}
  mx  = {t:0 for t in oprs}
  for t1,t2,s1,s2,_ in played:
    tbp[t1] += s1; tbp[t2] += s2
    if s1 > s2:   rp[t1] += 2
    elif s2 > s1: rp[t2] += 2
    else:         rp[t1] += 1; rp[t2] += 1
    mx[t1] = max(mx[t1], s1); mx[t2] = max(mx[t2], s2)
  world_high = max(mx.values()) if mx else 0

  # build progression
  teams  = sorted({t for m in played for t in m[:2]})
  labels = list(range(1, len(played)+1))
  team_hist = {t: [] for t in teams}
  for i in range(1, len(played)+1):
    hist_opr = oprcalc(played[:i])
    for t in teams:
      team_hist[t].append(round(hist_opr.get(t, 0.0), 2))

  return render_template_string("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>ASPIRE OPR Calculator</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
  body { 
    background: #f0f2f5; 
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; 
    padding: 2rem;
  }
  .container { 
    max-width: 1100px; 
    background: white; 
    border-radius: 12px;
    box-shadow: 0 0.5rem 1.5rem rgba(0,0,0,0.08); 
    padding: 2rem;
    margin-bottom: 2rem;
  }
  .header { 
    background: linear-gradient(135deg, #4a6cf7, #1e40af);
    color: white; 
    padding: 2rem 1.5rem;
    border-radius: 10px; 
    text-align: center; 
    margin-bottom: 2rem;
    box-shadow: 0 4px 12px rgba(74, 108, 247, 0.2);
  }
  .card {
    border: none;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    margin-bottom: 1.5rem;
  }
  .card-header {
    border-bottom: none;
    padding: 1rem 1.5rem;
    font-weight: 600;
    border-radius: 10px 10px 0 0 !important;
  }
  .card-body {
    padding: 1.5rem;
  }
  .table {
    margin-bottom: 0;
  }
  .table th {
    border-top: none;
    font-weight: 600;
  }
  .team-row:hover { 
    background: #f8fafd;
  }
  .top-team { 
    font-weight: bold; 
    background: rgba(74, 108, 247, 0.08);
  }
  .badge {
    font-size: 1rem;
    padding: 0.5rem 1rem;
    border-radius: 8px;
  }
  .bg-primary {
    background: #4a6cf7 !important;
  }
  .bg-secondary {
    background: #5c6ac4 !important;
  }
  .bg-success {
    background: #10b981 !important;
  }
  a {
    color: #4a6cf7;
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  </style>
</head>
<body>
  <div class="container">
  <div class="header">
    <h1>FTC OPR Calculator</h1>
    <p class="mb-0">All-Team OPR Progression (Qual + Finals)</p>
  </div>

  <!-- Chart -->
  <div class="card">
    <div class="card-body">
    <canvas id="allChart" height="220"></canvas>
    </div>
  </div>

  <div class="text-center mb-4 mt-4">
    <span class="h5">World Highscore:</span>
    <span class="badge bg-success ms-2">{{ world_high }}</span>
  </div>

  <!-- Rankings -->
  <div class="card">
    <div class="card-header bg-primary text-white">
    <h2 class="h5 mb-0">Team Rankings</h2>
    </div>
    <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead class="table-light">
      <tr>
        <th>#</th>
        <th>Team</th>
        <th>OPR</th>
        <th>RP</th>
        <th>TBP</th>
        <th>Max</th>
      </tr>
      </thead>
      <tbody>
      {% for team, opr in oprs.items() %}
      <tr class="team-row {% if loop.first %}top-team{% endif %}">
        <td>{{ loop.index }}</td>
        <td><a href="/team/{{team}}" target="_blank">{{ team }}</a></td>
        <td>{{"%.2f"|format(opr)}}</td>
        <td>{{ rp[team] }}</td>
        <td>{{ tbp[team] }}</td>
        <td>{{ mx[team] }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>

  <!-- Match History with Type -->
  <div class="card">
    <div class="card-header bg-secondary text-white">
    <h2 class="h5 mb-0">Match History</h2>
    </div>
    <div class="card-body p-0">
    <table class="table table-striped mb-0">
      <thead>
      <tr>
        <th>#</th>
        <th>Type</th>
        <th>Team 1</th>
        <th>Score 1</th>
        <th>Team 2</th>
        <th>Score 2</th>
      </tr>
      </thead>
      <tbody>
      {% for m in played %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ m[4] }}</td>
        <td>{{ m[0] }}</td>
        <td>{{ m[2] }}</td>
        <td>{{ m[1] }}</td>
        <td>{{ m[3] }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>
  </div>

  <script>
  const labels = {{ labels|tojson }};
  const teamHist = {{ team_hist|tojson }};
  const datasets = Object.entries(teamHist).map(([team, data]) => {
    const r = () => Math.floor(Math.random() * 200);
    const color = `rgb(${r()}, ${r()}, ${r()})`;
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

  new Chart(
    document.getElementById("allChart"),
    {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { 
      legend: { 
        position: "bottom",
        labels: {
        padding: 20,
        usePointStyle: true
        }
      },
      tooltip: {
        mode: 'index',
        intersect: false
      }
      },
      interaction: {
      mode: 'nearest',
      intersect: true
      },
      scales: {
      x: { 
        title: { 
        display: true, 
        text: "Match #",
        padding: 10
        },
        grid: {
        display: false
        }
      },
      y: { 
        title: { 
        display: true, 
        text: "OPR",
        padding: 10
        },
        grid: {
        color: '#f0f0f0'
        }
      }
      }
    }
    }
  );
  </script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
  """,
  oprs=oprs, rp=rp, tbp=tbp, mx=mx,
  world_high=world_high,
  played=played,
  labels=labels,
  team_hist=team_hist
  )

@app.route("/team/<team_number>")
def team_history(team_number):
  all_matches = fetch_matches_from_source()
  played = [(a,b,sa,sb,typ) for a,b,sa,sb,typ in all_matches if sa is not None and sb is not None]
  history = []
  for i in range(1, len(played)+1):
    h = oprcalc(played[:i])
    history.append({"match_idx": i, "opr": round(h.get(team_number, 0.0), 2)})
  return render_template_string("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>OPR Over Time: {{team}}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
  body { 
    background: #f0f2f5; 
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; 
    padding: 2rem;
  }
  .container {
    max-width: 800px;
    background: white;
    border-radius: 12px;
    padding: 2rem;
    box-shadow: 0 0.5rem 1.5rem rgba(0,0,0,0.08);
    margin-bottom: 2rem;
  }
  h1 {
    color: #333;
    margin-bottom: 1.5rem;
  }
  .card {
    border: none;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    margin-bottom: 1.5rem;
  }
  .back-link {
    display: inline-block;
    margin-top: 1rem;
    color: #4a6cf7;
    text-decoration: none;
  }
  .back-link:hover {
    text-decoration: underline;
  }
  </style>
</head>
<body>
  <div class="container">
  <h1>OPR Over Time: {{team}}</h1>
  <div class="card">
    <div class="card-body">
    <canvas id="chart" height="300"></canvas>
    </div>
  </div>
  <a href="/" class="back-link">← Back to Rankings</a>
  </div>
  <script>
  const history = {{ history|tojson }};
  new Chart(document.getElementById("chart"), {
    type: "line",
    data: {
    labels: history.map(x => x.match_idx),
    datasets: [{ 
      label: "OPR", 
      data: history.map(x => x.opr), 
      fill: false, 
      tension: 0.2,
      borderColor: '#4a6cf7',
      backgroundColor: 'rgba(74, 108, 247, 0.1)',
      borderWidth: 3,
      pointRadius: 4
    }]
    },
    options: {
    responsive: true,
    plugins: {
      legend: {
      display: false
      },
      tooltip: {
      callbacks: {
        title: (items) => `Match #${items[0].label}`,
        label: (item) => `OPR: ${item.raw}`
      }
      }
    },
    scales: {
      x: { 
      title: { 
        display: true, 
        text: "Match #",
        padding: 10
      },
      grid: {
        display: false
      }
      },
      y: { 
      title: { 
        display: true, 
        text: "OPR",
        padding: 10
      },
      grid: {
        color: '#f0f0f0'
      }
      }
    }
    }
  });
  </script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
  """, team=team_number, history=history)

if __name__ == "__main__":
  app.run(debug=True)
