(() => {
  "use strict";

  const canvas = document.getElementById("matrix-rain");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const characters = "01ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzアイウエオカキクケコサシスセソタチツテトナニヌネノ#$%&*+-=<>[]{}";
  const fontSize = 15;
  const trailMin = 8;
  const trailMax = 20;
  const maxFrameMs = 34;
  let width = 0;
  let height = 0;
  let columns = 0;
  let drops = [];
  let trails = [];
  let raf = 0;
  let lastDrawAt = 0;

  function resetColumn(index, initial = false) {
    trails[index] = trailMin + Math.floor(Math.random() * (trailMax - trailMin + 1));
    drops[index] = initial
      ? Math.floor(Math.random() * (Math.ceil(height / fontSize) + 28)) - 18
      : Math.floor(Math.random() * -18);
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = Math.max(1, Math.floor(canvas.clientWidth));
    height = Math.max(1, Math.floor(canvas.clientHeight));
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    columns = Math.ceil(width / fontSize);
    drops = Array.from({ length: columns });
    trails = Array.from({ length: columns });
    for (let i = 0; i < columns; i += 1) resetColumn(i, true);

    lastDrawAt = 0;
    draw(true, performance.now());
  }

  function draw(firstFrame = false, now = performance.now()) {
    if (!firstFrame && now - lastDrawAt < maxFrameMs) {
      raf = window.requestAnimationFrame((timestamp) => draw(false, timestamp));
      return;
    }

    lastDrawAt = now;
    ctx.fillStyle = "rgba(1, 5, 2, 0.075)";
    ctx.fillRect(0, 0, width, height);
    ctx.font = fontSize + "px monospace";
    ctx.textBaseline = "top";

    for (let i = 0; i < columns; i += 1) {
      const headY = drops[i] * fontSize;
      const length = trails[i] || trailMin;

      for (let j = 0; j < length; j += 1) {
        const y = headY - j * fontSize;
        if (y < -fontSize || y > height + fontSize) continue;

        const head = j === 0;
        const alpha = Math.max(0.045, (1 - j / length) * (head ? 0.98 : 0.72));
        ctx.fillStyle = head
          ? `rgba(218,255,210,${alpha})`
          : `rgba(57,255,20,${alpha})`;
        ctx.shadowBlur = head ? 8 : 2;
        ctx.shadowColor = "#39ff14";
        const char = characters[(Math.random() * characters.length) | 0];
        ctx.fillText(char, i * fontSize, y);
      }
    }
    ctx.shadowBlur = 0;

    for (let i = 0; i < columns; i += 1) {
      if (drops[i] * fontSize > height + (trails[i] || trailMin) * fontSize) {
        if (Math.random() > 0.90) resetColumn(i);
      } else {
        drops[i] += 1;
      }
    }

    if (!firstFrame && !reduceMotion) {
      raf = window.requestAnimationFrame((timestamp) => draw(false, timestamp));
    }
  }

  function start() {
    resize();
    window.addEventListener("resize", resize, { passive: true });
  }

  window.addEventListener("pagehide", () => {
    if (raf) window.cancelAnimationFrame(raf);
  }, { once: true });

  start();
})();
