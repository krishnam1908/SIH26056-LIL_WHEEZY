'use strict';

const express = require('express');
const router = express.Router();
const streamEngine = require('../services/streamEngine');

/**
 * GET /api/stream/status
 * Returns current continuous stream state and metrics
 */
router.get('/status', (req, res) => {
  res.json({
    success: true,
    stream: streamEngine.getStatus()
  });
});

/**
 * POST /api/stream/start
 * Starts continuous scraping with configurable batch size and cooldown
 * Body: { batchSize: 10, cooldownMs: 3000, carriers: [...], routes: [...] }
 */
router.post('/start', (req, res) => {
  const options = req.body || {};
  const status = streamEngine.start(options);
  res.json({
    success: true,
    message: `Continuous stream started (Batch size: ${status.batchSize}, Cooldown: ${status.cooldownMs}ms)`,
    stream: status
  });
});

/**
 * POST /api/stream/pause
 * Temporarily pauses the stream loop
 */
router.post('/pause', (req, res) => {
  const status = streamEngine.pause();
  res.json({
    success: true,
    message: 'Continuous stream paused',
    stream: status
  });
});

/**
 * POST /api/stream/resume
 * Resumes a paused stream loop
 */
router.post('/resume', (req, res) => {
  const status = streamEngine.resume();
  res.json({
    success: true,
    message: 'Continuous stream resumed',
    stream: status
  });
});

/**
 * POST /api/stream/stop
 * Completely stops the continuous stream
 */
router.post('/stop', (req, res) => {
  const status = streamEngine.stop();
  res.json({
    success: true,
    message: 'Continuous stream stopped',
    stream: status
  });
});

module.exports = router;
