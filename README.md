# Airfare Price Index (APIx)

**National Statistical Office (NSO, MoSPI) & Reserve Bank of India (RBI) Retail Inflation & Price Intelligence Platform**

An integrated, production-grade macroeconomic intelligence platform and real-time analytical engine that computes official Consumer Price Index (CPI) transport inflation sub-indices for Indian domestic civil aviation. Scrapes real-time flight quotes from all major carriers (**Air India**, **IndiGo**, **Akasa Air**, **SpiceJet**, **Air India Express**) across **28+ domestic flight routes** connecting **16+ primary airport hubs** with **15,121+ verified live quotes**.

Computes daily **Laspeyres**, **Paasche**, and **Fisher Ideal** geometric mean inflation indices, **STL seasonal adjustment filters**, **ARIMA time-series machine learning forecasts**, and provides an **Interactive SVG Route Network Map** with automated nationwide flight tours.

```
Live Booking Engines (Direct HTTP REST & Reverse-Engineered IBE REST APIs)
   ↓  Autonomous Continuous Stream Engine · Residential Proxy Mesh (5 Nodes) · SHA1 Dedupe
MongoDB Atlas  (flight_fares.fares  -  15,121+ Documents)
   ↓
NSO Dual-Index & STL Seasonal Adjustment Engine (indexEngine.js) + ARIMA ML Forecasting (arimaEngine.js)
   ↓
Express REST API  (/api/stats, /api/fares/analytics, /api/apix/dual-index, /api/capacity-weights, /api/stream...)
   ↓  fetch() / Server-Sent Events (SSE)
Frontend Dashboard  (Vanilla HTML5 / CSS3 / ES6 JS / SVG Map Engine)
```

---

## Tech Stack & Architecture

| Layer | Technology | Key Capabilities |
|---|---|---|
| **Frontend** | HTML5, Vanilla CSS3, Vanilla ES6 JS | Zero external UI dependencies, dynamic SVG route map with `<animateMotion>` airplane looping animation, dark/light themes, KaTeX math typesetting. |
| **Backend** | Node.js, Express.js | High-speed REST APIs, Server-Sent Events (SSE) streaming (`/api/stream`), 15s in-memory caching layer. |
| **Scraper Infrastructure** | Hybrid Python Direct HTTP + Node.js Adapters | Zero-Playwright Direct HTTP REST scrapers (~1.1s response), Akasa REST IBE direct connectors (~0.5s response), anti-detection TLS fingerprints. |
| **Autonomous Stream Engine** | Continuous Worker Loop (`streamEngine.js`) | Background route rotation, live quote broadcasting, REST lifecycle controls (`/api/stream/start`, `pause`, `resume`, `stop`). |
| **Analytical Engine** | NSO / MoSPI Dual-Index Engine (`indexEngine.js`) | Laspeyres ($I_L$), Paasche ($I_P$), Fisher Ideal ($I_F$) indices, STL Day-of-Week Seasonal Decomposition ($SA_t = Y_t / S_t$). |
| **Forecasting Engine** | ARIMA $(p,d,q)$ + Seasonal Model (`arimaEngine.js`) | 7, 14, and 30-day forecast horizons, 95% Confidence Intervals, surge pricing alerts (+12%, +22%, +35%), 5-axis Route Outage Vulnerability Radar. |
| **Database** | MongoDB Atlas, Mongoose | SHA1 deduplication key `SHA1(origin|dest|date|airline|flightNo|class|source)`, compound indexes for sub-millisecond query response across 15,121+ records. |
| **Residential Proxy Mesh** | Regional Node Rotation (`proxyMeshService.js`) | 5 Indian IP nodes (`IN-DEL`, `IN-BOM`, `IN-BLR`, `IN-CCU`, `IN-HYD`) with HTTP/2 TLS Client Hello rotation. |

---

## Core Platform Features

### 1. Autonomous Continuous Scraping Stream Engine
- **Non-Stop Background Ingestion**: Automatically cycles across 28+ domestic routes and 5 carriers, continuously refreshing live quotes.
- **Server-Sent Events (SSE)**: Streams live quote updates to connected browser clients over `GET /api/stream`.
- **Lifecycle & Telemetry Controls**: Start, pause, resume, and stop stream loops via REST endpoints while monitoring worker memory and query throughput.

### 2. Interactive SVG India Route Network Map
- **Geo-Calibrated Vector Geometry**: Accurate vector paths for all 36 Indian States and Union Territories from Simplemaps.
- **Airport Hub Coordinates**: 16+ calibrated airport nodes strictly positioned inside their geographic state boundaries (`DEL`, `BOM`, `BLR`, `MAA`, `CCU`, `HYD`, `AMD`, `PNQ`, `GOI`, `JAI`, `LKO`, `PAT`, `GAU`, `SXR`, `TRV`, `COK`, `BBI`, `IXC`, etc.).
- **Dynamic Route Highlighting & Looping Plane**: Renders quadratic bezier curves with green origin and amber destination pulse beacons, traversed by an SVG airplane in a continuous animation loop.
- **"All Origins $\to$ All Destinations" Nationwide Flight Tour**: Automated tour loop that sequentially highlights and flies every domestic flight route in India one-by-one in an infinite cycle.

### 3. NSO / MoSPI Dual-Index & Central Bank Inflation Engine
- **Laspeyres Base-Weighted Price Index ($I_L$)**: Base-period passenger traffic weighted price index ($I_L = \frac{\sum P_t Q_0}{\sum P_0 Q_0} \times 100$).
- **Paasche Current-Weighted Price Index ($I_P$)**: Current-period passenger traffic weighted price index ($I_P = \frac{\sum P_t Q_t}{\sum P_0 Q_t} \times 100$).
- **Fisher Ideal Geometric Mean Index ($I_F$)**: Official NSO (MoSPI) & RBI CPI transport inflation standard ($I_F = \sqrt{I_L \cdot I_P}$).
- **STL Seasonal Decomposition**: Strips weekly and festive demand surges to isolate core underlying inflation ($SA_t = Y_t / \tilde{S}_k$).
- **DGCA Capacity Weights ($W_c$)**: Weighted using DGCA monthly Available Seat-Kilometers (ASK) and Passenger Load Factors (PLF) (`IndiGo 51.5%`, `Air India Group 23.8%`, `SpiceJet 13.1%`, `Akasa Air 11.6%`).

### 4. ARIMA Machine Learning Time-Series Forecasting
- **Point Forecast ($\hat{Y}_{t+h}$)**: Combines AutoRegression ($p$), Differencing ($d$), Moving Average ($q$), and 7-day cyclical seasonality.
- **95% Confidence Intervals**: Mathematical upper/lower risk envelopes ($\text{CI}_{95\%} = \hat{Y}_{t+h} \pm 1.96 \cdot \sigma_e \sqrt{h}$).
- **Surge Alerts & Outage Risk Radar**: Flags price surges (+12% Moderate, +22% High, +35% Critical) and evaluates 5-axis route capacity stress.

### 5. Interactive DGCA Policy Scenario Simulator
- Live multi-variable simulator on `analysis.html` featuring dual sliders for **DGCA Weight ($w_r$)** and **Simulated Price ($P_r$)**, calculating instant point contributions ($\Delta I_{\text{sector}}$) to headline national inflation under ATF fuel tax hikes or festival surges.

### 6. Carrier Scraper Adapters, Fallbacks & Ingestion Mechanics

| Airline | Primary Adapter | Fallback / Alternative | Key Mechanics |
|---|---|---|---|
| **Akasa Air** | `Direct IBE REST API` | `Apify Google Flights Actor` | Requests guest session tokens via `POST /api/ibe/token/generateToken` on `prod-bl.qp.akasaair.com` and queries `POST /api/ibe/availability/search` for real seat buckets, base fare, taxes, and UDF splits. Also supports multi-market grid queries. |
| **IndiGo** | `Direct HTTP Scraper` | `Apify Actor (johnvc/google-flights...)` | Default is browser-free / token-free direct HTTP GET via `http_direct_scraper.py`. Filters by carrier code `6E` and IndiGo identifiers. |
| **Air India** | `Direct HTTP Scraper` | `Apify Actor` | Direct HTTP extraction targeting mainline `AI` flights (excludes Express). |
| **SpiceJet** | `Direct HTTP Scraper` | `Apify Actor` | Direct HTTP extraction targeting `SG` flights. |
| **Air India Express** | `Direct HTTP Scraper` | `Apify Actor` | Direct HTTP extraction filtering for `IX` / `I5` flights (distinct from mainline Air India). |
| **DGCA** | `DGCA Service` | `S3 Mirror / Local PDF` | Downloads official monthly air traffic statistics reports from DGCA, extracts passenger counts, and calculates carrier capacity weights. |

### 7. End-to-End Scraper Workflow & 6-Stage Ingestion Pipeline
```
[1. Input Matrix] → [2. Proxy Mesh & Evasion] → [3. Schema Extraction] → [4. QA & Outliers] → [5. SHA1 Dedupe] → [6. DB Upsert & SSE Stream]
```
1. **Input Normalization & Matrix Expansion (`normalize_input`)**: Expands requested route pairs, travel dates, and airline source adapters into a Cartesian execution matrix with strict 3-letter IATA code validation and route-isolated failure boundaries.
2. **Anti-Detection, Proxy Routing & Evasion (`proxyMeshService`)**: Rotates requests across 5 regional Indian proxy nodes (`IN-DEL`, `IN-BOM`, `IN-BLR`, `IN-CCU`, `IN-HYD`) with HTTP/2 TLS Client Hello fingerprint randomization, high-speed direct HTTP REST scraping (`http_direct_scraper.py`), or direct IBE REST execution.
3. **Data Extraction & Price Decomposition**: Unbundles airline search results into canonical fare fields: `baseFare`, `taxes`, `udfFee`, `convenienceFee`, and `totalFare` in INR currency alongside flight metadata.
4. **Validation & Outlier Quality Rules (`fare_validator`, `outlier_detector`)**: Enforces hard price boundaries ($\text{₹}100 \le P_{\text{total}} \le \text{₹}100,000$) and fee consistency ($|P_{\text{total}} - \sum P_{\text{comp}}| \le \max(\text{₹}100, 0.20 \cdot P_{\text{total}})$), tagging non-standard quotes with `dataQuality: 'OUTLIER'`.
5. **Cryptographic Deduplication (`attach_dedupe_keys`)**: Computes deterministic SHA1 hash keys `SHA1(origin|dest|date|airline|flightNo|class|source)` to guarantee idempotent writes.
6. **Multi-Tier Persistence & Live Event Broadcasting (`streamEngine`)**: Atomically upserts records to MongoDB Atlas (`flight_fares.fares`), writes JSONL audit logs, and pushes real-time `quote_update` events via Server-Sent Events (`GET /api/stream`).

---

## REST API Reference

| Method | Endpoint | Parameters / Body | Description |
|---|---|---|---|
| `GET` | `/api/health` | None | System health and MongoDB Atlas connection status |
| `GET` | `/api/stats` | None | Aggregated KPIs across 15,121+ verified quotes, 28+ routes, and carriers |
| `GET` | `/api/fares/analytics` | `origin`, `destination`, `airline`, `days` | Pan-India or route-specific analytics, 9-bin histogram, min/max/avg, and elasticity |
| `GET` | `/api/fares/route/:origin/:destination` | Path params: `:origin`, `:destination` | Raw flight quotes for a specific route sector |
| `GET` | `/api/apix/dual-index` | `baseDate` | NSO Laspeyres, Paasche, and Fisher Ideal Dual-Index series |
| `GET` | `/api/apix?seasonal=true` | `seasonal=true` | Seasonally-Adjusted (SA) Core Inflation Index |
| `GET` | `/api/capacity-weights` | None | DGCA seat capacity (ASK) & load factor (PLF) carrier weight distributions |
| `GET` | `/api/heatmap` | None | 2D sector route fare matrix |
| `GET` | `/api/elasticity` | `origin`, `destination` | Lead-time advance purchase price curve ($T+1$ to $T+45$) |
| `GET` | `/api/forecast/arima` | `origin`, `destination`, `p`, `d`, `q`, `horizon` | ARIMA point price predictions, confidence intervals, and $R^2$/RMSE metrics |
| `GET` | `/api/forecast/surges` | `origin`, `destination` | High-probability dynamic surge pricing alerts |
| `GET` | `/api/forecast/outages` | `origin`, `destination` | 5-axis Route Outage Vulnerability Radar scores |
| `GET` | `/api/stream` | None | Server-Sent Events (SSE) live real-time quote stream |
| `GET` | `/api/stream/status` | None | Autonomous continuous stream engine status and worker telemetry |
| `POST` | `/api/stream/start` | `{ batchSize, cooldownMs }` | Start background continuous scraping stream loop |
| `POST` | `/api/stream/pause` | None | Pause continuous scraping stream loop |
| `POST` | `/api/stream/resume` | None | Resume paused stream loop |
| `POST` | `/api/stream/stop` | None | Stop continuous scraping stream worker |
| `GET` | `/api/scrape/mesh/status` | None | Active residential proxy node mesh health |
| `GET` | `/api/scrape/queue/status` | None | Active scraper worker queue status |
| `POST` | `/api/scrape/queue/dispatch` | `{ source, origin, destination, travelDate }` | Dispatch asynchronous scrape job to worker queue |
| `GET` | `/api/meta` | None | Airport hubs, route pairs, airlines, and date metadata |
| `GET` | `/api/nso-export` | `month`, `year`, `format=csv` | Official NSO/MoSPI format monthly CPI report |
| `GET` | `/api/backtest` | None | 30-Day back-tested DGCA benchmark verification |

---

## CLI & Parallel Worker Pool Execution

### 1. Scrape Single Route:
```bash
python -m backend.scraper_python.cli --source airindia --origin DEL --destination BOM --date 2026-09-15
```

### 2. Scrape All Registered Airlines (Air India, IndiGo, Akasa, SpiceJet):
```bash
python -m backend.scraper_python.cli --source airindia,indigo,akasa,spicejet --origin DEL --destination BOM --date 2026-09-15
```

### 3. Run Master 30-Day Full Route Batch Suite:
```bash
python -u backend/scripts/run_30_day_unbuffered.py
```

### 4. Run High-Speed Multi-Worker Parallel Scraper Pool (4-8 Concurrent Workers):
```bash
python backend/scripts/run_parallel_workers.py --workers 4 --days 30 --sources airindia,indigo,akasa,spicejet
```

### 5. Control Autonomous Continuous Stream Engine via cURL:
```bash
# Start Stream
curl -X POST http://localhost:5000/api/stream/start -H "Content-Type: application/json" -d '{"batchSize": 10, "cooldownMs": 3000}'

# Pause Stream
curl -X POST http://localhost:5000/api/stream/pause

# Resume Stream
curl -X POST http://localhost:5000/api/stream/resume

# Check Stream Status
curl http://localhost:5000/api/stream/status
```

---

## Running the Web Application

Start the backend server (serves both REST API and frontend static assets):

```bash
npm start
# or: node backend/server.js
```

Open your browser:
- `http://localhost:5000/`  -  Executive Overview & CPI Dashboard
- `http://localhost:5000/routes.html`  -  Interactive SVG India Route Network & Nationwide Flight Tour
- `http://localhost:5000/analysis.html`  -  Dual-Index Analytics & DGCA Policy Scenario Simulator
- `http://localhost:5000/forecasting.html`  -  ARIMA Machine Learning Price Forecasting & Outage Alerts
- `http://localhost:5000/data.html`  -  Autonomous Continuous Scraping Stream Engine & Data Monitor
- `http://localhost:5000/docs.html`  -  Technical Documentation & Interactive REST API Console

---

## License & Compliance

Developed for the **National Statistical Office (NSO, MoSPI)** and **Reserve Bank of India (RBI)** for official domestic airfare inflation sub-index measurement and macroeconomic policy modeling under DGCA guidelines.
