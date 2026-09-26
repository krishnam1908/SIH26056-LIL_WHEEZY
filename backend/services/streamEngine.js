'use strict';

/**
 * streamEngine.js
 * Continuous Scraping Stream Engine for APIx (5 Parallel Scraper Workers)
 * 
 * Provides an automated, perpetual producer-consumer stream that:
 * 1. Coordinates 5 concurrent scraper workers in parallel (Akasa, IndiGo, Air India, SpiceJet, Air India Express).
 * 2. Cycles through high-traffic metro routes and advance booking windows.
 * 3. Streams individual quotes live over SSE directly into the UI in real time.
 * 4. Buffers quotes and atomically commits batches of target size (e.g. 10 quotes) to MongoDB Atlas.
 * 5. Uses idempotent deduplication, configurable cooldowns, and full worker health tracking.
 * 6. Supports start, pause, resume, and stop controls via REST and UI.
 */

const { spawn } = require('child_process');
const path = require('path');
const { saveFaresIdempotent } = require('../utils/fareStore');

const DEFAULT_ROUTES = [
  { origin: 'DEL', destination: 'BLR' },
  { origin: 'BOM', destination: 'DEL' },
  { origin: 'DEL', destination: 'BOM' },
  { origin: 'BLR', destination: 'DEL' },
  { origin: 'BOM', destination: 'BLR' },
  { origin: 'DEL', destination: 'CCU' },
  { origin: 'HYD', destination: 'DEL' },
  { origin: 'MAA', destination: 'DEL' },
  { origin: 'DEL', destination: 'GOI' },
  { origin: 'BOM', destination: 'HYD' }
];

const DEFAULT_CARRIERS = ['akasa', 'indigo', 'airindia', 'spicejet', 'airindiaexpress'];
const ADVANCE_DAYS_LIST = [1, 3, 7, 14, 21, 30];

class StreamEngine {
  constructor() {
    this.status = 'IDLE'; // 'IDLE', 'RUNNING', 'PAUSED', 'STOPPED'
    this.batchSize = 10;
    this.cooldownMs = 1500;
    this.workerCount = 5;
    this.activeWorkers = 0;
    this.carriers = [...DEFAULT_CARRIERS];
    this.workerStatuses = {
      akasa: 'IDLE',
      indigo: 'IDLE',
      airindia: 'IDLE',
      spicejet: 'IDLE',
      airindiaexpress: 'IDLE'
    };

    this.routes = [...DEFAULT_ROUTES];
    this.advanceDays = [...ADVANCE_DAYS_LIST];

    this.routeIndex = 0;
    this.dayIndex = 0;

    this.buffer = [];
    this.totalBatchesSaved = 0;
    this.totalQuotesScraped = 0;
    this.totalQuotesInserted = 0;
    this.totalQuotesSkipped = 0;

    this.currentRoute = 'DEL-BLR';
    this.currentCarrier = '5 Workers Parallel (All Airlines)';
    this.currentTravelDate = new Date().toISOString().slice(0, 10);

    this.startedAt = null;
    this.lastBatchAt = null;
    this.recentBatches = [];

    this._broadcastFn = null;
    this._loopRunning = false;
    this._sleepTimer = null;
  }

  setBroadcastFn(fn) {
    this._broadcastFn = fn;
  }

  broadcast(type, data) {
    if (typeof this._broadcastFn === 'function') {
      try {
        this._broadcastFn(type, data);
      } catch (err) {
        console.warn('[StreamEngine] broadcast error:', err.message);
      }
    }
  }

  getStatus() {
    return {
      status: this.status,
      batchSize: this.batchSize,
      cooldownMs: this.cooldownMs,
      workerCount: this.workerCount,
      activeWorkers: this.activeWorkers,
      workerStatuses: { ...this.workerStatuses },
      bufferLength: this.buffer.length,
      totalBatchesSaved: this.totalBatchesSaved,
      totalQuotesScraped: this.totalQuotesScraped,
      totalQuotesInserted: this.totalQuotesInserted,
      totalQuotesSkipped: this.totalQuotesSkipped,
      currentRoute: this.currentRoute,
      currentCarrier: this.currentCarrier,
      currentTravelDate: this.currentTravelDate,
      startedAt: this.startedAt,
      lastBatchAt: this.lastBatchAt,
      recentBatches: this.recentBatches.slice(-10)
    };
  }

  start(options = {}) {
    if (this.status === 'RUNNING') {
      return this.getStatus();
    }

    if (options.batchSize && Number(options.batchSize) > 0) {
      this.batchSize = Math.max(1, Math.min(100, parseInt(options.batchSize, 10)));
    }
    if (options.cooldownMs && Number(options.cooldownMs) >= 0) {
      this.cooldownMs = Math.max(500, Math.min(60000, parseInt(options.cooldownMs, 10)));
    }
    if (Array.isArray(options.carriers) && options.carriers.length > 0) {
      this.carriers = options.carriers;
    }
    if (Array.isArray(options.routes) && options.routes.length > 0) {
      this.routes = options.routes;
    }
    if (options.workers && Number(options.workers) > 0) {
      this.workerCount = Math.max(1, Math.min(10, parseInt(options.workers, 10)));
    } else {
      this.workerCount = this.carriers.length;
    }

    this.status = 'RUNNING';
    if (!this.startedAt) {
      this.startedAt = new Date().toISOString();
    }

    console.log(`[StreamEngine] 🚀 Started continuous stream with ${this.workerCount} parallel workers (Batch Size: ${this.batchSize}, Cooldown: ${this.cooldownMs}ms)`);
    this.broadcast('stream_status', this.getStatus());

    if (!this._loopRunning) {
      this._runLoop();
    }

    return this.getStatus();
  }

  pause() {
    if (this.status === 'RUNNING') {
      this.status = 'PAUSED';
      console.log('[StreamEngine] Continuous stream paused.');
      this.broadcast('stream_status', this.getStatus());
    }
    return this.getStatus();
  }

  resume() {
    if (this.status === 'PAUSED' || this.status === 'STOPPED') {
      this.status = 'RUNNING';
      console.log('[StreamEngine] Continuous stream resumed.');
      this.broadcast('stream_status', this.getStatus());
      if (!this._loopRunning) {
        this._runLoop();
      }
    }
    return this.getStatus();
  }

  stop() {
    this.status = 'STOPPED';
    this.activeWorkers = 0;
    for (const c of Object.keys(this.workerStatuses)) {
      this.workerStatuses[c] = 'IDLE';
    }
    console.log('[StreamEngine] Continuous stream stopped.');
    this.broadcast('stream_status', this.getStatus());
    return this.getStatus();
  }

  async _sleep(ms) {
    return new Promise(resolve => {
      this._sleepTimer = setTimeout(resolve, ms);
    });
  }

  _getPythonBin() {
    if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
    return process.platform === 'win32' ? 'python' : 'python3';
  }

  _fetchCell(carrier, origin, destination, travelDate) {
    return new Promise(resolve => {
      const scriptPath = path.join(__dirname, '..', 'scraper_python', 'stream_fetcher.py');
      const rootDir = path.join(__dirname, '..', '..');
      const pythonBin = this._getPythonBin();

      const child = spawn(pythonBin, [scriptPath, carrier, origin, destination, travelDate], {
        cwd: rootDir,
        shell: process.platform === 'win32'
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', d => { stdout += d; });
      child.stderr.on('data', d => { stderr += d; });

      child.on('close', code => {
        if (code !== 0 && stderr) {
          console.warn(`[StreamEngine] Scraper ${carrier} non-zero exit (${code}):`, stderr.slice(0, 300));
        }
        try {
          const parsed = JSON.parse(stdout.trim());
          if (parsed && Array.isArray(parsed.fares)) {
            return resolve(parsed.fares);
          }
        } catch (e) {
          if (stdout.trim().length > 0) {
            console.warn(`[StreamEngine] JSON parse error for ${carrier}:`, e.message, stdout.slice(0, 200));
          }
        }
        resolve([]);
      });

      child.on('error', err => {
        console.error(`[StreamEngine] fetch cell error (${carrier} ${origin}-${destination} using ${pythonBin}):`, err.message);
        resolve([]);
      });
    });
  }

  async _saveBatch(quotesToSave) {
    const batchNumber = this.totalBatchesSaved + 1;
    this.lastBatchAt = new Date().toISOString();

    let saveResult = { insertedCount: 0, skippedCount: 0 };
    try {
      saveResult = await saveFaresIdempotent(quotesToSave);
    } catch (err) {
      console.error(`[StreamEngine] saveBatch #${batchNumber} error:`, err.message);
    }

    this.totalBatchesSaved++;
    this.totalQuotesScraped += quotesToSave.length;
    this.totalQuotesInserted += saveResult.insertedCount || 0;
    this.totalQuotesSkipped += saveResult.skippedCount || 0;

    const batchEvent = {
      batchNumber,
      quotesInBatch: quotesToSave.length,
      inserted: saveResult.insertedCount || 0,
      skipped: saveResult.skippedCount || 0,
      carrier: this.currentCarrier,
      route: this.currentRoute,
      travelDate: this.currentTravelDate,
      totalSavedSoFar: this.totalQuotesScraped,
      timestamp: this.lastBatchAt
    };

    this.recentBatches.push(batchEvent);
    if (this.recentBatches.length > 50) {
      this.recentBatches.shift();
    }

    console.log(`[StreamEngine] 💾 Batch #${batchNumber} Saved: ${quotesToSave.length} quotes (${saveResult.insertedCount} inserted, ${saveResult.skippedCount} deduplicated) for ${this.currentCarrier} on ${this.currentRoute}`);

    this.broadcast('stream_batch_saved', batchEvent);
    this.broadcast('stream_status', this.getStatus());
  }

  async _runLoop() {
    this._loopRunning = true;

    while (this.status === 'RUNNING' || this.status === 'PAUSED') {
      if (this.status === 'PAUSED') {
        await this._sleep(1000);
        continue;
      }

      // Step 1: Drain any existing full batches from buffer before launching next cycle
      while (this.buffer.length >= this.batchSize && this.status === 'RUNNING') {
        const batch = this.buffer.splice(0, this.batchSize);
        await this._saveBatch(batch);
        if (this.status !== 'RUNNING') break;
        await this._sleep(150);
      }

      if (this.status !== 'RUNNING') continue;

      // Step 2: Select next target route and travel date
      const activeRoutes = this.routes.length > 0 ? this.routes : DEFAULT_ROUTES;
      const routeObj = activeRoutes[this.routeIndex % activeRoutes.length];
      const advanceDay = this.advanceDays[this.dayIndex % this.advanceDays.length];

      const targetDate = new Date();
      targetDate.setDate(targetDate.getDate() + advanceDay);
      const travelDateStr = targetDate.toISOString().slice(0, 10);

      this.currentRoute = `${routeObj.origin}-${routeObj.destination}`;
      this.currentCarrier = '5 Parallel Workers (Akasa, IndiGo, Air India, SpiceJet, AI Express)';
      this.currentTravelDate = travelDateStr;

      // Advance sector and day indices for the next cycle
      this.routeIndex++;
      if (this.routeIndex % activeRoutes.length === 0) {
        this.dayIndex++;
      }

      const carriersToRun = this.carriers.length > 0 ? this.carriers : DEFAULT_CARRIERS;
      this.workerCount = carriersToRun.length;
      this.activeWorkers = carriersToRun.length;

      for (const c of carriersToRun) {
        this.workerStatuses[c] = 'SCRAPING';
      }

      this.broadcast('stream_status', this.getStatus());
      console.log(`[StreamEngine] ⚡ Executing 5 parallel workers: [${carriersToRun.join(', ')}] on ${routeObj.origin} -> ${routeObj.destination} for ${travelDateStr}`);

      // Step 3: Run all 5 workers concurrently in parallel!
      const workerPromises = carriersToRun.map(async (carrier) => {
        try {
          const incoming = await this._fetchCell(carrier, routeObj.origin, routeObj.destination, travelDateStr);
          const count = incoming ? incoming.length : 0;
          this.workerStatuses[carrier] = `IDLE (${count} quotes)`;

          if (incoming && incoming.length > 0) {
            for (const item of incoming) {
              item.isLive = true;
              if (!item.source || item.source === 'scraper' || item.source === 'direct-http') {
                item.source = carrier;
              }
              this.buffer.push(item);
              // Broadcast quote live to frontend SSE listener immediately
              this.broadcast('quote_update', item);
            }
          }
        } catch (err) {
          this.workerStatuses[carrier] = `ERROR (${err.message})`;
          console.warn(`[StreamEngine] Worker error on ${carrier}:`, err.message);
        } finally {
          this.activeWorkers = Math.max(0, this.activeWorkers - 1);
          this.broadcast('stream_status', this.getStatus());
        }
      });

      // Wait for all 5 concurrent workers to finish fetching their fares
      await Promise.allSettled(workerPromises);
      this.activeWorkers = 0;

      // Step 4: Drain and save batches of configured size (e.g. 10 quotes each)
      while (this.buffer.length >= this.batchSize && this.status === 'RUNNING') {
        const batch = this.buffer.splice(0, this.batchSize);
        await this._saveBatch(batch);
        if (this.status !== 'RUNNING') break;
        await this._sleep(150);
      }

      // Step 5: Flush any trailing quotes in buffer immediately so none linger
      if (this.buffer.length > 0 && this.status === 'RUNNING') {
        const remaining = this.buffer.splice(0, this.buffer.length);
        await this._saveBatch(remaining);
      }

      // Inter-sector cooldown delay before triggering the next sector
      if (this.status === 'RUNNING') {
        await this._sleep(this.cooldownMs);
      }
    }

    this._loopRunning = false;
    this.activeWorkers = 0;
    for (const c of Object.keys(this.workerStatuses)) {
      this.workerStatuses[c] = 'IDLE';
    }
    this.broadcast('stream_status', this.getStatus());
  }
}

// Singleton instance
const streamEngine = new StreamEngine();

module.exports = streamEngine;
