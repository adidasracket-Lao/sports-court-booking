const courtBackground = (sketch) => {
  const palette = {
    paper: [246, 243, 235],
    ink: [30, 31, 26],
    green: [18, 102, 79],
    amber: [191, 91, 4],
    blue: [48, 93, 116],
  };

  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let particles = [];

  sketch.setup = () => {
    const canvas = sketch.createCanvas(window.innerWidth, window.innerHeight);
    canvas.parent("p5-background");
    canvas.elt.setAttribute("aria-hidden", "true");
    sketch.pixelDensity(Math.min(window.devicePixelRatio || 1, 2));
    buildParticles();
  };

  sketch.windowResized = () => {
    sketch.resizeCanvas(window.innerWidth, window.innerHeight);
    buildParticles();
  };

  sketch.draw = () => {
    drawBase();
    drawCourtGrid();
    drawScanLines();
    drawParticles();

    if (prefersReducedMotion.matches) {
      sketch.noLoop();
    }
  };

  function buildParticles() {
    const count = Math.floor(sketch.map(Math.min(sketch.width, 1600), 320, 1600, 28, 78, true));
    particles = Array.from({ length: count }, (_, index) => ({
      x: sketch.random(sketch.width),
      y: sketch.random(sketch.height),
      size: sketch.random(1.2, 3.4),
      speed: sketch.random(0.08, 0.32),
      drift: sketch.random(-0.12, 0.12),
      phase: sketch.random(sketch.TWO_PI),
      tone: index % 4 === 0 ? palette.amber : palette.green,
    }));
  }

  function drawBase() {
    sketch.clear();
    const ctx = sketch.drawingContext;
    const gradient = ctx.createLinearGradient(0, 0, sketch.width, sketch.height);
    gradient.addColorStop(0, "rgba(248, 246, 240, 0.72)");
    gradient.addColorStop(0.48, "rgba(224, 238, 228, 0.68)");
    gradient.addColorStop(1, "rgba(244, 239, 228, 0.72)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, sketch.width, sketch.height);

    drawGlow(sketch.width * 0.16, sketch.height * 0.12, sketch.width * 0.45, palette.amber, 0.22);
    drawGlow(sketch.width * 0.86, sketch.height * 0.24, sketch.width * 0.5, palette.green, 0.26);
    drawGlow(sketch.width * 0.58, sketch.height * 0.92, sketch.width * 0.55, palette.blue, 0.18);
  }

  function drawGlow(x, y, radius, color, alpha) {
    const ctx = sketch.drawingContext;
    const glow = ctx.createRadialGradient(x, y, 0, x, y, radius);
    glow.addColorStop(0, `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`);
    glow.addColorStop(1, `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0)`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, sketch.width, sketch.height);
  }

  function drawCourtGrid() {
    const cx = sketch.width * 0.5;
    const top = sketch.height * 0.08;
    const bottom = sketch.height * 0.96;
    const topWidth = sketch.width * 0.3;
    const bottomWidth = sketch.width * 1.1;

    sketch.push();
    sketch.noFill();
    sketch.strokeWeight(1);

    for (let i = 0; i <= 8; i += 1) {
      const t = i / 8;
      const y = sketch.lerp(top, bottom, Math.pow(t, 1.45));
      const width = sketch.lerp(topWidth, bottomWidth, t);
      const alpha = sketch.lerp(90, 22, t);
      sketch.stroke(palette.green[0], palette.green[1], palette.green[2], alpha);
      sketch.line(cx - width / 2, y, cx + width / 2, y);
    }

    for (let i = -3; i <= 3; i += 1) {
      const topX = cx + i * (topWidth / 6);
      const bottomX = cx + i * (bottomWidth / 6);
      sketch.stroke(palette.green[0], palette.green[1], palette.green[2], i === 0 ? 80 : 48);
      sketch.line(topX, top, bottomX, bottom);
    }

    sketch.stroke(palette.amber[0], palette.amber[1], palette.amber[2], 65);
    sketch.strokeWeight(1.4);
    sketch.line(cx - topWidth * 0.36, top + 34, cx + bottomWidth * 0.34, bottom - 60);
    sketch.line(cx + topWidth * 0.36, top + 34, cx - bottomWidth * 0.34, bottom - 60);
    sketch.pop();
  }

  function drawScanLines() {
    const time = sketch.frameCount * 0.006;
    const bandY = (sketch.sin(time) * 0.5 + 0.5) * sketch.height;

    sketch.push();
    sketch.strokeWeight(1);
    for (let i = 0; i < 5; i += 1) {
      const y = bandY + i * 18;
      const alpha = 28 - i * 4;
      sketch.stroke(palette.blue[0], palette.blue[1], palette.blue[2], alpha);
      sketch.line(sketch.width * 0.08, y, sketch.width * 0.92, y - sketch.height * 0.04);
    }
    sketch.pop();
  }

  function drawParticles() {
    sketch.push();
    sketch.noStroke();
    particles.forEach((particle) => {
      const shimmer = sketch.sin(sketch.frameCount * 0.02 + particle.phase) * 0.5 + 0.5;
      sketch.fill(particle.tone[0], particle.tone[1], particle.tone[2], 45 + shimmer * 90);
      sketch.circle(particle.x, particle.y, particle.size + shimmer * 1.4);

      if (!prefersReducedMotion.matches) {
        particle.y -= particle.speed;
        particle.x += particle.drift + sketch.sin(sketch.frameCount * 0.01 + particle.phase) * 0.08;
      }

      if (particle.y < -12) {
        particle.y = sketch.height + 12;
        particle.x = sketch.random(sketch.width);
      }
    });
    sketch.pop();
  }
};

new p5(courtBackground);
