(() => {
  'use strict';

  const VERSION = '20260429-pass7-blockbusters-single';
  const $ = (id) => document.getElementById(id);
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));
  const rand = (lo, hi) => lo + Math.random() * (hi - lo);
  const irand = (lo, hi) => Math.floor(rand(lo, hi + 1));
  const dist = (a, b, c, d) => Math.hypot(a - c, b - d);

  const assetBase = './assets/images/block_busters_web/';
  const spriteNames = [
    'reptilian', 'monkey', 'skeleton', 'alien', 'mantis', 'witch',
    'fatman', 'blob', 'robot', 'cyber', 'pixie', 'knight'
  ];
  const botNames = [
    ['REPTILIAN', 'reptilian'], ['MONKEY', 'monkey'], ['SKELETON', 'skeleton'],
    ['ALIEN', 'alien'], ['MANTIS', 'mantis'], ['WITCH', 'witch'], ['FATMAN', 'fatman']
  ];

  const state = {
    keys: Object.create(null),
    mouse: { x: 0, y: 0, down: false, clicked: false },
    paused: false,
    muted: false,
    audioReady: false,
    audioCtx: null,
    assets: { blocks: [], players: {}, boss: null, loaded: 0, total: 0 },
    world: null,
    last: 0
  };

  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text;
  }

  function loadImage(src) {
    state.assets.total += 1;
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => { state.assets.loaded += 1; };
    img.onerror = () => { state.assets.loaded += 1; img.failed = true; };
    img.src = `${src}?v=${encodeURIComponent(VERSION)}`;
    return img;
  }

  function loadAssets() {
    for (let i = 1; i <= 10; i += 1) {
      state.assets.blocks[i] = loadImage(`${assetBase}block_${i}.png`);
    }
    state.assets.boss = loadImage(`${assetBase}boss_blob.png`);
    spriteNames.forEach((name) => {
      state.assets.players[name] = [];
      for (let i = 0; i < 4; i += 1) {
        state.assets.players[name][i] = loadImage(`${assetBase}player_${name}_${i}.png`);
      }
    });
  }

  function key(name) {
    return !!state.keys[name] || !!state.keys[name.toLowerCase()];
  }

  function initAudio() {
    if (state.audioReady) return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    try {
      state.audioCtx = new AudioContext();
      state.audioReady = true;
    } catch {
      state.audioReady = false;
    }
  }

  function playTone(freq = 220, length = 0.045, type = 'square', gain = 0.045) {
    if (state.muted) return;
    initAudio();
    const ctx = state.audioCtx;
    if (!ctx) return;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    const osc = ctx.createOscillator();
    const amp = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    amp.gain.value = 0.0001;
    osc.connect(amp);
    amp.connect(ctx.destination);
    const now = ctx.currentTime;
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0002, gain), now + 0.006);
    amp.gain.exponentialRampToValueAtTime(0.0001, now + length);
    osc.start(now);
    osc.stop(now + length + 0.015);
  }

  function updateMuteButton() {
    const btn = $('demoMuteBtn');
    if (!btn) return;
    btn.textContent = state.muted ? 'Audio Muted' : 'Mute Audio';
    btn.setAttribute('aria-pressed', state.muted ? 'true' : 'false');
  }

  function toggleMute() {
    state.muted = !state.muted;
    updateMuteButton();
    if (!state.muted) playTone(440, 0.04, 'sine', 0.025);
  }

  class BlockBustersWorld {
    constructor(w, h) {
      this.reset(w, h);
    }

    reset(w, h) {
      this.w = w;
      this.h = h;
      this.tile = 16;
      this.cols = 170;
      this.rows = 58;
      this.map = [];
      this.time = 0;
      this.gravity = 1;
      this.messageTimer = 3.5;
      this.message = 'BOSS DROPPING IN!';
      this.camera = { x: 0, y: 0 };
      this.particles = [];
      this.projectiles = [];
      this.powerups = [];
      this.meteors = [];
      this.bossTimer = 9;
      this.meteorTimer = 15;
      this.spawnMap();
      const spawnX = this.cols * this.tile * 0.53;
      const spawnY = this.topAtWorldX(spawnX) - 90;
      this.player = this.makeCharacter('YOU', 'reptilian', spawnX, spawnY, true);
      this.bots = botNames.map(([name, sprite], i) => {
        const x = spawnX + (i - 3) * 74;
        const y = this.topAtWorldX(x) - 70 - Math.random() * 160;
        const bot = this.makeCharacter(name, sprite, x, y, false);
        bot.score = irand(0, 8);
        return bot;
      });
      this.boss = { x: spawnX + 120, y: -100, vx: 0.9, vy: 0, hp: 32, active: false, sprite: 'boss' };
      this.seedPowerups();
    }

    makeCharacter(name, sprite, x, y, isPlayer) {
      return {
        name, sprite, x, y, vx: 0, vy: 0, w: 26, h: 34,
        hp: isPlayer ? 5 : 4, maxHp: isPlayer ? 5 : 4, score: 0,
        grounded: false, jumpCount: 0, facing: 1, dash: 0,
        aiThink: rand(0, 1), targetX: x, cooldown: 0, isPlayer
      };
    }

    spawnMap() {
      this.map = Array.from({ length: this.rows }, () => Array(this.cols).fill(0));
      const ground = Math.floor(this.rows * 0.68);
      for (let x = 0; x < this.cols; x += 1) {
        const wave = Math.sin(x * 0.11) * 2 + Math.sin(x * 0.037) * 3;
        const top = Math.floor(ground + wave + irand(-1, 1));
        for (let y = top; y < this.rows; y += 1) {
          const edge = y === top;
          let type = irand(1, 9);
          if (edge && Math.random() < 0.25) type = irand(1, 5);
          if (y > this.rows - 3 && Math.random() < 0.2) type = 10;
          this.map[y][x] = type;
        }
        if (Math.random() < 0.055) {
          const stack = irand(2, 6);
          for (let k = 1; k <= stack; k += 1) {
            const y = top - k;
            if (y > 8) this.map[y][x] = irand(1, 9);
          }
        }
      }
    }

    seedPowerups() {
      const kinds = ['heal', 'vital', 'dash', 'shield', 'frenzy', 'grow', 'haste', 'bomb', 'pulse', 'blast'];
      for (let i = 0; i < 8; i += 1) {
        const x = rand(360, this.cols * this.tile - 360);
        this.powerups.push({ x, y: rand(80, this.topAtWorldX(x) - 80), kind: kinds[i % kinds.length], r: 11, vy: rand(0.2, 0.9) });
      }
    }

    topAtWorldX(wx) {
      const col = clamp(Math.floor(wx / this.tile), 0, this.cols - 1);
      for (let y = 0; y < this.rows; y += 1) {
        if (this.map[y][col]) return y * this.tile;
      }
      return (this.rows - 1) * this.tile;
    }

    solidAt(wx, wy) {
      const x = Math.floor(wx / this.tile);
      const y = Math.floor(wy / this.tile);
      if (x < 0 || y < 0 || x >= this.cols || y >= this.rows) return false;
      return !!this.map[y][x];
    }

    breakBlockAt(wx, wy, owner = this.player) {
      const x = Math.floor(wx / this.tile);
      const y = Math.floor(wy / this.tile);
      if (x < 0 || y < 0 || x >= this.cols || y >= this.rows) return false;
      const type = this.map[y][x];
      if (!type || type === 10) return false;
      this.map[y][x] = 0;
      owner.score += 1;
      this.spawnParticles(x * this.tile + 8, y * this.tile + 8, type);
      if (Math.random() < 0.08) this.powerups.push({ x: x * this.tile + 8, y: y * this.tile - 22, kind: 'pulse', r: 11, vy: 0.4 });
      playTone(120 + type * 35, 0.035, 'square', 0.025);
      return true;
    }

    spawnParticles(x, y, type = 1) {
      for (let i = 0; i < 12; i += 1) {
        this.particles.push({ x, y, vx: rand(-90, 90), vy: rand(-130, 40), life: rand(0.25, 0.65), type });
      }
    }

    moveCharacter(c, dt, inputX = 0, wantsJump = false) {
      const speed = c.dash > 0 ? 350 : 175;
      c.vx += (inputX * speed - c.vx) * (c.grounded ? 0.18 : 0.08);
      c.dash = Math.max(0, c.dash - dt);
      if (inputX) c.facing = Math.sign(inputX);
      if (wantsJump && c.jumpLatch !== true && c.jumpCount < 2) {
        c.vy = -335 * this.gravity;
        c.grounded = false;
        c.jumpCount += 1;
        c.jumpLatch = true;
        playTone(c.isPlayer ? 330 : 260, 0.055, 'triangle', 0.022);
      }
      if (!wantsJump) c.jumpLatch = false;
      c.vy += 900 * this.gravity * dt;
      c.vy = clamp(c.vy, -620, 620);
      this.integrate(c, dt);
    }

    integrate(c, dt) {
      c.x += c.vx * dt;
      c.x = clamp(c.x, 24, this.cols * this.tile - 24);
      if (c.vx > 0 && this.solidAt(c.x + c.w * 0.5, c.y)) {
        c.x = Math.floor((c.x + c.w * 0.5) / this.tile) * this.tile - c.w * 0.5 - 1;
        c.vx *= -0.2;
      } else if (c.vx < 0 && this.solidAt(c.x - c.w * 0.5, c.y)) {
        c.x = (Math.floor((c.x - c.w * 0.5) / this.tile) + 1) * this.tile + c.w * 0.5 + 1;
        c.vx *= -0.2;
      }

      c.y += c.vy * dt;
      c.grounded = false;
      const footY = c.y + c.h * 0.5 * this.gravity;
      if (this.gravity > 0) {
        if (this.solidAt(c.x - c.w * 0.3, footY) || this.solidAt(c.x + c.w * 0.3, footY)) {
          c.y = Math.floor(footY / this.tile) * this.tile - c.h * 0.5 - 0.5;
          c.vy = 0;
          c.grounded = true;
          c.jumpCount = 0;
        }
      } else if (this.solidAt(c.x - c.w * 0.3, footY) || this.solidAt(c.x + c.w * 0.3, footY)) {
        c.y = (Math.floor(footY / this.tile) + 1) * this.tile + c.h * 0.5 + 0.5;
        c.vy = 0;
        c.grounded = true;
        c.jumpCount = 0;
      }
    }

    handlePlayer(dt) {
      let mx = 0;
      if (key('arrowleft') || key('a')) mx -= 1;
      if (key('arrowright') || key('d')) mx += 1;
      if ((key('shift') || key('shiftleft')) && !this.player.dash && Math.abs(mx) > 0) {
        this.player.dash = 0.18;
        this.player.vx += mx * 400;
        playTone(190, 0.06, 'sawtooth', 0.03);
      }
      const wantsJump = key('w') || key('arrowup');
      this.moveCharacter(this.player, dt, mx, wantsJump);
      this.player.cooldown = Math.max(0, this.player.cooldown - dt);
      if ((key(' ') || state.mouse.clicked) && this.player.cooldown <= 0) {
        this.shockwave(this.player);
        this.player.cooldown = 0.55;
      }
    }

    shockwave(owner) {
      const radius = 90;
      for (let yy = -radius; yy <= radius; yy += this.tile) {
        for (let xx = -radius; xx <= radius; xx += this.tile) {
          if (Math.hypot(xx, yy) <= radius && Math.random() < 0.28) {
            this.breakBlockAt(owner.x + xx, owner.y + yy, owner);
          }
        }
      }
      this.projectiles.push({ x: owner.x, y: owner.y, r: 18, life: 0.35, max: 0.35 });
      this.bots.forEach((bot) => {
        const d = dist(owner.x, owner.y, bot.x, bot.y);
        if (d < radius) {
          bot.vx += ((bot.x - owner.x) / Math.max(1, d)) * 360;
          bot.vy += ((bot.y - owner.y) / Math.max(1, d)) * 260;
          owner.score += 1;
        }
      });
      if (this.boss.active && dist(owner.x, owner.y, this.boss.x, this.boss.y) < radius * 1.2) {
        this.boss.hp -= 2;
        owner.score += 2;
      }
      playTone(95, 0.13, 'sawtooth', 0.045);
    }

    handleBots(dt) {
      this.bots.forEach((bot, i) => {
        bot.aiThink -= dt;
        if (bot.aiThink <= 0) {
          bot.aiThink = rand(0.45, 1.4);
          bot.targetX = this.player.x + rand(-280, 280);
          if (Math.random() < 0.35) bot.jumpRequest = true;
        }
        const dx = clamp((bot.targetX - bot.x) / 120, -1, 1);
        this.moveCharacter(bot, dt, dx, bot.jumpRequest);
        bot.jumpRequest = false;
        if (Math.random() < 0.003) this.breakBlockAt(bot.x + bot.facing * 24, bot.y + this.gravity * 24, bot);
        if (this.boss.active && i % 3 === 0 && Math.random() < 0.004) {
          this.boss.hp -= 1;
          bot.score += 1;
        }
      });
    }

    handleBoss(dt) {
      this.bossTimer -= dt;
      if (!this.boss.active && this.bossTimer <= 0) {
        this.boss.active = true;
        this.boss.y = -60;
        this.boss.vy = 80;
        this.message = 'GLEEBS DROPPING IN!';
        this.messageTimer = 2.5;
        playTone(70, 0.2, 'sawtooth', 0.04);
      }
      if (!this.boss.active) return;
      this.boss.x += Math.sin(this.time * 0.9) * 36 * dt + this.boss.vx * 25 * dt;
      this.boss.y += this.boss.vy * dt;
      const targetY = this.topAtWorldX(this.boss.x) - 300 + Math.sin(this.time * 1.1) * 22;
      this.boss.y += (targetY - this.boss.y) * 0.015;
      if (this.boss.x < this.player.x - 360 || this.boss.x > this.player.x + 360) this.boss.vx *= -1;
      if (this.boss.hp <= 0) {
        this.message = 'GLEEBS BROKEN — YOU BECAME BOSS!';
        this.messageTimer = 3;
        this.player.score += 25;
        this.spawnParticles(this.boss.x, this.boss.y, 4);
        this.boss.active = false;
        this.boss.hp = 32;
        this.bossTimer = 11;
        playTone(520, 0.18, 'triangle', 0.045);
      }
    }

    handlePowerups(dt) {
      this.powerups.forEach((p) => {
        p.y += p.vy * 24 * dt * this.gravity;
        const top = this.topAtWorldX(p.x) - 18;
        if (this.gravity > 0 && p.y > top) p.y = top;
        if (dist(p.x, p.y, this.player.x, this.player.y) < 34) {
          this.player.score += 5;
          this.player.hp = clamp(this.player.hp + 1, 0, this.player.maxHp);
          p.dead = true;
          playTone(660, 0.07, 'sine', 0.035);
        }
      });
      this.powerups = this.powerups.filter(p => !p.dead);
      if (this.powerups.length < 8 && Math.random() < 0.012) {
        const x = rand(this.camera.x + 100, this.camera.x + this.w - 100);
        this.powerups.push({ x, y: this.camera.y + 40, kind: 'drop', r: 11, vy: rand(0.3, 1.2) });
      }
    }

    handleMeteors(dt) {
      this.meteorTimer -= dt;
      if (this.meteorTimer <= 0) {
        this.meteorTimer = rand(10, 18);
        this.meteors.push({ x: this.camera.x + rand(120, this.w - 120), y: this.camera.y - 100, vx: rand(-80, 80), vy: rand(280, 430), life: 6 });
      }
      this.meteors.forEach((m) => {
        m.x += m.vx * dt;
        m.y += m.vy * dt;
        m.life -= dt;
        if (this.solidAt(m.x, m.y)) {
          for (let i = 0; i < 24; i += 1) this.breakBlockAt(m.x + rand(-45, 45), m.y + rand(-45, 45), this.player);
          this.spawnParticles(m.x, m.y, 5);
          m.dead = true;
          playTone(130, 0.18, 'sawtooth', 0.04);
        }
      });
      this.meteors = this.meteors.filter(m => !m.dead && m.life > 0);
    }

    updateParticles(dt) {
      this.particles.forEach((p) => {
        p.vy += 360 * dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.life -= dt;
      });
      this.particles = this.particles.filter(p => p.life > 0);
      this.projectiles.forEach((p) => { p.life -= dt; });
      this.projectiles = this.projectiles.filter(p => p.life > 0);
    }

    update(dt, w, h) {
      this.w = w; this.h = h; this.time += dt;
      if (state.paused) return;
      this.messageTimer = Math.max(0, this.messageTimer - dt);
      this.handlePlayer(dt);
      this.handleBots(dt);
      this.handleBoss(dt);
      this.handlePowerups(dt);
      this.handleMeteors(dt);
      this.updateParticles(dt);
      const viewScale = Math.max(0.9, Math.min(w / 1600, h / 900) * 1.35);
      const desiredX = this.player.x - (w / viewScale) * 0.5;
      const desiredY = this.player.y - (h / viewScale) * 0.46;
      this.camera.x += (desiredX - this.camera.x) * 0.12;
      this.camera.y += (desiredY - this.camera.y) * 0.08;
      this.camera.x = clamp(this.camera.x, 0, this.cols * this.tile - (w / viewScale));
      this.camera.y = clamp(this.camera.y, -280, this.rows * this.tile - (h / viewScale) + 140);
    }

    drawBackground(ctx, w, h) {
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, '#040914');
      g.addColorStop(0.54, '#07111d');
      g.addColorStop(1, '#031820');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      for (let i = 0; i < 180; i += 1) {
        const x = (i * 173.37 + this.time * (i % 5)) % w;
        const y = (i * 71.11 + Math.sin(i) * 20) % Math.max(1, h * 0.74);
        const hue = i % 3 === 0 ? '#6ee8ff' : (i % 4 === 0 ? '#ff66f2' : '#70ffd6');
        ctx.fillStyle = hue;
        ctx.globalAlpha = 0.25 + (i % 6) * 0.1;
        ctx.fillRect(x, y, i % 7 === 0 ? 2 : 1, i % 7 === 0 ? 2 : 1);
      }
      ctx.globalAlpha = 1;
      const base = h * 0.64;
      for (let layer = 0; layer < 3; layer += 1) {
        ctx.fillStyle = `rgba(${15 + layer * 6},${35 + layer * 9},${56 + layer * 15},${0.18 + layer * 0.08})`;
        ctx.beginPath();
        ctx.moveTo(0, h);
        for (let x = 0; x <= w + 80; x += 70) {
          const y = base + layer * 30 + Math.sin(x * 0.012 + this.time * 0.12 + layer) * 24;
          ctx.lineTo(x, y);
        }
        ctx.lineTo(w, h);
        ctx.closePath();
        ctx.fill();
      }
    }

    drawTile(ctx, type, sx, sy, size) {
      const img = state.assets.blocks[type];
      if (img && img.complete && !img.failed) {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(img, sx, sy, size, size);
        return;
      }
      const colors = ['#000', '#50beff', '#a05f37', '#50ffdc', '#c85aff', '#ffa046', '#50ff78', '#ff5050', '#78dc78', '#ffe678', '#141419'];
      ctx.fillStyle = colors[type] || '#5bf';
      ctx.fillRect(sx, sy, size, size);
      ctx.strokeStyle = 'rgba(255,255,255,.28)';
      ctx.strokeRect(sx + 1, sy + 1, size - 2, size - 2);
    }

    drawMap(ctx, w, h) {
      const size = Math.max(12, Math.floor(Math.min(w / 100, 18)));
      const scale = size / this.tile;
      const minX = Math.max(0, Math.floor(this.camera.x / this.tile) - 2);
      const maxX = Math.min(this.cols, Math.ceil((this.camera.x + w / scale) / this.tile) + 3);
      const minY = Math.max(0, Math.floor(this.camera.y / this.tile) - 2);
      const maxY = Math.min(this.rows, Math.ceil((this.camera.y + h / scale) / this.tile) + 3);
      ctx.save();
      ctx.scale(scale, scale);
      for (let y = minY; y < maxY; y += 1) {
        for (let x = minX; x < maxX; x += 1) {
          const type = this.map[y][x];
          if (!type) continue;
          this.drawTile(ctx, type, x * this.tile - this.camera.x, y * this.tile - this.camera.y, this.tile);
        }
      }
      ctx.restore();
    }

    drawSprite(ctx, sprite, frame, x, y, flip = false, scale = 3) {
      const img = state.assets.players[sprite]?.[frame % 4];
      ctx.save();
      ctx.translate(x, y);
      if (flip) ctx.scale(-1, 1);
      ctx.imageSmoothingEnabled = false;
      if (img && img.complete && !img.failed) {
        ctx.drawImage(img, -12 * scale, -18 * scale, 24 * scale, 24 * scale);
      } else {
        ctx.fillStyle = '#7df0ff';
        ctx.beginPath();
        ctx.arc(0, -10 * scale, 9 * scale, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillRect(-7 * scale, -8 * scale, 14 * scale, 17 * scale);
      }
      ctx.restore();
    }

    drawCharacter(ctx, c, scale) {
      const sx = (c.x - this.camera.x) * scale;
      const sy = (c.y - this.camera.y) * scale;
      const frame = Math.floor(this.time * 8 + Math.abs(c.vx) * 0.02) % 4;
      ctx.save();
      ctx.scale(1, this.gravity < 0 ? -1 : 1);
      const drawY = this.gravity < 0 ? -sy : sy;
      if (c.isPlayer) {
        ctx.fillStyle = 'rgba(120,220,255,.15)';
        ctx.beginPath();
        ctx.arc(sx, drawY - 16 * scale, 34 * scale + Math.sin(this.time * 5) * 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(120,255,255,.65)';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      this.drawSprite(ctx, c.sprite, frame, sx, drawY, c.facing < 0, scale);
      ctx.restore();
      ctx.font = `800 ${Math.max(11, 12 * scale / 3)}px Consolas, monospace`;
      ctx.textAlign = 'center';
      ctx.fillStyle = c.isPlayer ? '#f7ffff' : '#dce2f4';
      ctx.shadowColor = 'rgba(0,0,0,.9)';
      ctx.shadowBlur = 4;
      ctx.fillText(c.name, sx, sy - 48 * scale / 3);
      ctx.shadowBlur = 0;
    }

    drawBoss(ctx, scale) {
      if (!this.boss.active) return;
      const sx = (this.boss.x - this.camera.x) * scale;
      const sy = (this.boss.y - this.camera.y) * scale;
      ctx.save();
      ctx.translate(sx, sy);
      const glowR = 52 * scale;
      const glow = ctx.createRadialGradient(0, 0, 8, 0, 0, glowR);
      glow.addColorStop(0, 'rgba(255,180,255,.48)');
      glow.addColorStop(1, 'rgba(80,210,255,0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(0, 0, glowR, 0, Math.PI * 2);
      ctx.fill();
      const img = state.assets.boss;
      ctx.imageSmoothingEnabled = false;
      if (img && img.complete && !img.failed) ctx.drawImage(img, -36, -36, 72, 72);
      else { ctx.fillStyle = '#ffb5ff'; ctx.beginPath(); ctx.arc(0, 0, 28, 0, Math.PI * 2); ctx.fill(); }
      ctx.restore();
      ctx.font = '800 15px Consolas, monospace';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#ffc8ff';
      ctx.fillText('GLEEBS', sx, sy - 48);
      ctx.fillStyle = 'rgba(255,255,255,.14)';
      ctx.fillRect(sx - 42, sy - 37, 84, 7);
      ctx.fillStyle = '#ff64d4';
      ctx.fillRect(sx - 42, sy - 37, 84 * clamp(this.boss.hp / 32, 0, 1), 7);
    }

    drawPowerups(ctx, scale) {
      this.powerups.forEach((p) => {
        const sx = (p.x - this.camera.x) * scale;
        const sy = (p.y - this.camera.y) * scale;
        const r = (p.r + Math.sin(this.time * 5 + p.x) * 2) * scale;
        ctx.fillStyle = 'rgba(120,255,170,.23)';
        ctx.beginPath(); ctx.arc(sx, sy, r * 1.7, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#78ff9f';
        ctx.fillRect(sx - r * 0.8, sy - r * 0.8, r * 1.6, r * 1.6);
        ctx.strokeStyle = '#d8ffe4';
        ctx.strokeRect(sx - r * 0.8, sy - r * 0.8, r * 1.6, r * 1.6);
      });
    }

    drawEffects(ctx, scale) {
      this.projectiles.forEach((p) => {
        const t = p.life / p.max;
        ctx.strokeStyle = `rgba(120,255,255,${t * 0.8})`;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc((p.x - this.camera.x) * scale, (p.y - this.camera.y) * scale, p.r * (2.8 - t) * scale, 0, Math.PI * 2);
        ctx.stroke();
      });
      this.particles.forEach((p) => {
        const x = (p.x - this.camera.x) * scale;
        const y = (p.y - this.camera.y) * scale;
        ctx.globalAlpha = clamp(p.life * 2, 0, 1);
        this.drawTile(ctx, p.type, x, y, 4 * scale);
      });
      ctx.globalAlpha = 1;
      this.meteors.forEach((m) => {
        const x = (m.x - this.camera.x) * scale;
        const y = (m.y - this.camera.y) * scale;
        ctx.strokeStyle = 'rgba(255,210,140,.55)';
        ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(x - 35, y - 58); ctx.lineTo(x, y); ctx.stroke();
        ctx.fillStyle = '#ffb56b'; ctx.fillRect(x - 8, y - 8, 16, 16);
      });
    }

    drawLeader(ctx, w) {
      const pool = [this.player, ...this.bots].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
      const champ = pool[0];
      const x = w / 2;
      const y = 92;
      ctx.save();
      ctx.fillStyle = 'rgba(8,18,28,.64)';
      ctx.beginPath(); ctx.arc(x, y, 66, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = 'rgba(80,255,255,.42)'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x, y, 54 + Math.sin(this.time * 2) * 4, 0, Math.PI * 2); ctx.stroke();
      this.drawSprite(ctx, champ.sprite, Math.floor(this.time * 7) % 4, x, y + 14, false, 2.8);
      ctx.textAlign = 'center';
      ctx.font = '800 13px Consolas, monospace';
      ctx.fillStyle = '#5ddcff'; ctx.fillText('LEADER', x, y + 83);
      ctx.fillStyle = '#c9d7f6'; ctx.fillText(champ.name, x, y + 103);
      ctx.fillStyle = '#96a5bd'; ctx.fillText(`SCORE ${champ.score}`, x, y + 123);
      ctx.restore();
    }

    drawHud(ctx) {
      const top = [this.player, ...this.bots].sort((a, b) => b.score - a.score)[0];
      const lines = [
        ['SETTINGS', '#5ef5ff'],
        ['O: OPEN SETTINGS', '#e4e6ff'],
        ['GRAVITY', '#5ef5ff'],
        [`GRAVITY: ${this.gravity < 0 ? 'INVERTED' : 'NORMAL'}`, '#e4e6ff'],
        ['VIEW: 100%', '#b8c0d8'],
        ['SCORES', '#5ef5ff'],
        [`YOU: REPTILIAN  HP ${this.player.hp}/${this.player.maxHp}  SCORE ${this.player.score}`, '#e4e6ff'],
        [`TOP: ${top.name}  SCORE ${top.score}`, '#e4e6ff'],
        ['BOSS', '#5ef5ff'],
        [`HP: ${this.boss.active ? Math.max(0, Math.ceil(this.boss.hp)) : 'WAITING'}`, '#e4e6ff'],
        ['ACTIVITY', '#5ef5ff'],
        [this.messageTimer > 0 ? this.message : 'BREAK BLOCKS • GRAB POWERUPS', '#c8d0ea']
      ];
      const x = 16, y = 16, row = 19, pad = 12;
      ctx.save();
      ctx.font = '800 15px Consolas, monospace';
      const width = 310;
      const height = lines.length * row + pad * 2;
      ctx.fillStyle = 'rgba(5, 9, 18, .78)';
      ctx.fillRect(x, y, width, height);
      ctx.strokeStyle = 'rgba(80,140,210,.75)';
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, width, height);
      lines.forEach((line, i) => {
        ctx.fillStyle = line[1];
        ctx.fillText(line[0], x + pad, y + pad + 14 + i * row);
      });
      ctx.restore();
    }

    drawPause(ctx, w, h) {
      if (!state.paused) return;
      ctx.fillStyle = 'rgba(0,0,0,.55)';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#f5f8ff';
      ctx.font = '900 44px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('PAUSED', w / 2, h / 2);
    }

    draw(ctx, w, h) {
      const scale = Math.max(0.9, Math.min(w / 1600, h / 900) * 1.35);
      this.drawBackground(ctx, w, h);
      ctx.save();
      this.drawMap(ctx, w, h);
      this.drawPowerups(ctx, scale);
      this.bots.forEach(bot => this.drawCharacter(ctx, bot, scale));
      this.drawCharacter(ctx, this.player, scale);
      this.drawBoss(ctx, scale);
      this.drawEffects(ctx, scale);
      ctx.restore();
      this.drawLeader(ctx, w);
      this.drawHud(ctx);
      this.drawPause(ctx, w, h);
    }
  }

  function resizeCanvas() {
    const canvas = $('demoCanvas');
    if (!canvas) return;
    const shell = canvas.parentElement;
    const rect = shell.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const cssW = Math.max(480, Math.floor(rect.width - 20));
    const cssH = Math.max(300, Math.floor(cssW * 9 / 16));
    canvas.style.height = `${cssH}px`;
    const w = Math.floor(cssW * ratio);
    const h = Math.floor(cssH * ratio);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      if (state.world) {
        state.world.w = w;
        state.world.h = h;
      }
    }
  }

  function canvasPoint(ev) {
    const canvas = $('demoCanvas');
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / Math.max(1, rect.width);
    const sy = canvas.height / Math.max(1, rect.height);
    return { x: (ev.clientX - rect.left) * sx, y: (ev.clientY - rect.top) * sy };
  }

  function bindInput() {
    window.addEventListener('keydown', (ev) => {
      const k = ev.key === ' ' ? ' ' : ev.key.toLowerCase();
      state.keys[k] = true;
      if ([' ', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k) && document.activeElement === $('demoCanvas')) ev.preventDefault();
      if (k === 'p') state.paused = !state.paused;
      if (k === 'm') toggleMute();
      if (k === 'r' && state.world) state.world.reset($('demoCanvas').width, $('demoCanvas').height);
      if (k === 'g' && state.world && !state.gravityLatch) {
        state.world.gravity *= -1;
        state.gravityLatch = true;
        state.world.message = state.world.gravity < 0 ? 'GRAVITY INVERTED' : 'GRAVITY NORMAL';
        state.world.messageTimer = 2.2;
        playTone(420, 0.09, 'triangle', 0.035);
      }
    });
    window.addEventListener('keyup', (ev) => {
      const k = ev.key === ' ' ? ' ' : ev.key.toLowerCase();
      state.keys[k] = false;
      if (k === 'g') state.gravityLatch = false;
    });
    const canvas = $('demoCanvas');
    if (canvas) {
      canvas.addEventListener('pointermove', ev => { Object.assign(state.mouse, canvasPoint(ev)); });
      canvas.addEventListener('pointerdown', ev => {
        initAudio();
        Object.assign(state.mouse, canvasPoint(ev), { down: true, clicked: true });
        canvas.focus({ preventScroll: true });
      });
      canvas.addEventListener('pointerup', () => { state.mouse.down = false; });
      canvas.addEventListener('pointerleave', () => { state.mouse.down = false; });
    }
    const mute = $('demoMuteBtn');
    if (mute) mute.addEventListener('click', () => { initAudio(); toggleMute(); });
    window.addEventListener('resize', resizeCanvas);
  }

  function frame(now) {
    const canvas = $('demoCanvas');
    if (!canvas || !state.world) return requestAnimationFrame(frame);
    resizeCanvas();
    const ctx = canvas.getContext('2d');
    const dt = Math.min(0.033, Math.max(0.001, (now - (state.last || now)) / 1000));
    state.last = now;
    state.world.update(dt, canvas.width, canvas.height);
    state.world.draw(ctx, canvas.width, canvas.height);
    state.mouse.clicked = false;
    requestAnimationFrame(frame);
  }

  function initText() {
    setText('demoSectionTitle', 'Block Busters — Neon Arena Web Demo');
    setText('demoSectionIntro', 'One focused browser demo inspired by the original Block Busters prototype. The multi-demo gallery has been removed so this can look and feel closer to the desktop build.');
    setText('demoStatus', 'Playable now');
    setText('demoTitle', 'Block Busters');
    setText('demoSummary', 'Pixel blocks, gravity flip, bot chaos, powerups, meteors, Gleebs boss pressure, and low-volume arcade feedback.');
    setText('demoObjective', 'Break blocks, grab powerups, outscore the bots, and survive Gleebs dropping into the arena.');
    setText('demoControls', 'A/D or Arrows move, W/Up jump, G flips gravity, Space shockwave, Shift dash, R reset, P pause, M mute.');
    setText('demoDetails', 'Audio starts low by default and can be muted. The demo uses original Block Busters pixel/block art where available with generated fallbacks.');
    setText('demoSectionNote', 'Single-game pass: the thumbnail grid and edit-manifest button are removed. Replace site images through assets/images/site_current/ and keep the same filenames for safest updates.');
    updateMuteButton();
  }

  function init() {
    if (window.__GM_BLOCK_BUSTERS_SINGLE_INIT__) return;
    window.__GM_BLOCK_BUSTERS_SINGLE_INIT__ = true;
    const canvas = $('demoCanvas');
    if (!canvas) return;
    document.body.classList.add('demo-runtime-ready', 'single-demo-runtime');
    const overlay = $('demoLoadingOverlay');
    if (overlay) overlay.hidden = true;
    initText();
    loadAssets();
    resizeCanvas();
    state.world = new BlockBustersWorld(canvas.width, canvas.height);
    bindInput();
    requestAnimationFrame(frame);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
