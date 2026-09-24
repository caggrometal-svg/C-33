(() => {
  "use strict";

  const canvas = document.getElementById("matrix-rain");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const characters = "01ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzアイウエオカキクケコサシスセソタチツテトナニヌネノ#$%&*+-=<>[]{}";
  const fontSize = 15;
  const resetChance = 0.975;
  let width = 0;
  let height = 0;
  let columns = 0;
  let drops = [];
  let frame = 0;
  let raf = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = Math.max(1, Math.floor(canvas.clientWidth));
    height = Math.max(1, Math.floor(canvas.clientHeight));
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    columns = Math.ceil(width / fontSize);
    drops = Array.from({ length: columns }, () =>
      Math.floor(Math.random() * -Math.max(4, height / fontSize))
    );
    draw(true);
  }

  function draw(firstFrame = false) {
    ctx.fillStyle = "rgba(1, 5, 2, 0.10)";
    ctx.fillRect(0, 0, width, height);

    ctx.font = fontSize + "px monospace";
    ctx.textBaseline = "top";

    for (let i = 0; i < columns; i += 1) {
      const y = drops[i] * fontSize;
      const char = characters[(Math.random() * characters.length) | 0];
      const head = Math.random() > 0.72;

      ctx.fillStyle = head
        ? "rgba(190,255,181,0.96)"
        : "rgba(57,255,20,0.66)";
      ctx.shadowBlur = head ? 7 : 3;
      ctx.shadowColor = "#39ff14";
      ctx.fillText(char, i * fontSize, y);
      ctx.shadowBlur = 0;

      if (y > height && Math.random() > resetChance) {
        drops[i] = Math.floor(Math.random() * -12);
      } else {
        drops[i] += 1;
      }
    }

    if (!firstFrame && !reduceMotion) {
      frame += 1;
      raf = window.requestAnimationFrame(() => {
        if (frame % 2 === 0) draw();
        else raf = window.requestAnimationFrame(draw);
      });
    }
  }

  function start() {
    resize();
    if (!reduceMotion) {
      window.addEventListener("resize", resize, { passive: true });
    }
  }

  window.addEventListener("pagehide", () => {
    if (raf) window.cancelAnimationFrame(raf);
  }, { once: true });

  start();
})();
