const { createCanvas } = require('canvas');
const GIFEncoder = require('gif-encoder-2');
const fs = require('fs');
const path = require('path');

const WIDTH = 480;
const HEIGHT = 360;

// 动作定义：每个动作包含名称、描述、动画帧生成函数
const actions = [
  {
    name: '头部前后活动',
    desc: '缓慢低头，再仰头',
    frames: 20,
    draw: (ctx, t) => {
      const angle = Math.sin(t * Math.PI * 2) * 20; // 前后±20度
      drawNeck(ctx, angle, 0);
    }
  },
  {
    name: '头部左右摆动',
    desc: '缓慢左倾，再右倾',
    frames: 20,
    draw: (ctx, t) => {
      const tilt = Math.sin(t * Math.PI * 2) * 20;
      drawNeck(ctx, 0, tilt);
    }
  },
  {
    name: '头部旋转',
    desc: '缓慢向左转，再向右转',
    frames: 20,
    draw: (ctx, t) => {
      const rotate = Math.sin(t * Math.PI * 2) * 30;
      drawNeckRotate(ctx, rotate);
    }
  },
  {
    name: '耸肩放松',
    desc: '双肩上耸，再放松下落',
    frames: 15,
    draw: (ctx, t) => {
      const shrug = Math.abs(Math.sin(t * Math.PI * 2)) * 20;
      drawShrug(ctx, shrug);
    }
  },
];

function drawBackground(ctx, actionName, desc) {
  // 渐变背景
  const grad = ctx.createLinearGradient(0, 0, 0, HEIGHT);
  grad.addColorStop(0, '#e8f5e9');
  grad.addColorStop(1, '#b2dfdb');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  // 标题
  ctx.fillStyle = '#1b5e20';
  ctx.font = 'bold 22px Arial';
  ctx.textAlign = 'center';
  ctx.fillText('颈椎健康操', WIDTH / 2, 36);

  // 动作名称
  ctx.fillStyle = '#2e7d32';
  ctx.font = 'bold 18px Arial';
  ctx.fillText(actionName, WIDTH / 2, 64);

  // 描述
  ctx.fillStyle = '#388e3c';
  ctx.font = '14px Arial';
  ctx.fillText(desc, WIDTH / 2, 86);

  // 底部提示
  ctx.fillStyle = '#666';
  ctx.font = '12px Arial';
  ctx.fillText('每天坚持，保护颈椎健康 ✓', WIDTH / 2, HEIGHT - 16);
}

function drawBody(ctx) {
  // 躯干
  ctx.fillStyle = '#4fc3f7';
  ctx.beginPath();
  ctx.roundRect(WIDTH/2 - 40, 210, 80, 90, 10);
  ctx.fill();
  ctx.strokeStyle = '#0288d1';
  ctx.lineWidth = 2;
  ctx.stroke();
}

function drawNeck(ctx, forwardAngle, tiltAngle) {
  const cx = WIDTH / 2;
  const cy = 200;

  ctx.save();
  ctx.translate(cx, cy + 10);

  // 绘制身体
  drawBody(ctx);

  // 颈部
  ctx.fillStyle = '#ffcc80';
  ctx.beginPath();
  ctx.roundRect(-10, -20, 20, 30, 4);
  ctx.fill();
  ctx.strokeStyle = '#e65100';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // 头部（倾斜）
  ctx.save();
  ctx.translate(0, -20);
  ctx.rotate((tiltAngle * Math.PI) / 180);
  // 前后偏移
  const fwdOffset = (forwardAngle / 20) * 12;
  ctx.translate(fwdOffset, 0);

  // 头
  ctx.fillStyle = '#ffe0b2';
  ctx.beginPath();
  ctx.ellipse(0, -28, 28, 32, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#bf360c';
  ctx.lineWidth = 2;
  ctx.stroke();

  // 眼睛
  ctx.fillStyle = '#333';
  ctx.beginPath();
  ctx.arc(-9, -30, 3.5, 0, Math.PI * 2);
  ctx.arc(9, -30, 3.5, 0, Math.PI * 2);
  ctx.fill();

  // 嘴巴
  ctx.strokeStyle = '#bf360c';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(0, -22, 7, 0.2, Math.PI - 0.2);
  ctx.stroke();

  // 箭头方向提示
  if (Math.abs(tiltAngle) > 5) {
    const arrowX = tiltAngle > 0 ? 48 : -48;
    drawArrow(ctx, 0, -28, arrowX, -28, tiltAngle > 0 ? '#e53935' : '#1e88e5');
  }
  if (Math.abs(forwardAngle) > 5) {
    const arrowY = forwardAngle > 0 ? -60 : 8;
    drawArrow(ctx, fwdOffset, -28, fwdOffset, arrowY, forwardAngle > 0 ? '#43a047' : '#fb8c00');
  }

  ctx.restore();
  ctx.restore();
}

function drawNeckRotate(ctx, rotateDeg) {
  const cx = WIDTH / 2;
  const cy = 200;

  ctx.save();
  ctx.translate(cx, cy + 10);
  drawBody(ctx);

  // 颈部
  ctx.fillStyle = '#ffcc80';
  ctx.beginPath();
  ctx.roundRect(-10, -20, 20, 30, 4);
  ctx.fill();
  ctx.strokeStyle = '#e65100';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  ctx.save();
  ctx.translate(0, -20);
  ctx.rotate((rotateDeg * Math.PI) / 180);

  ctx.fillStyle = '#ffe0b2';
  ctx.beginPath();
  ctx.ellipse(0, -28, 28, 32, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#bf360c';
  ctx.lineWidth = 2;
  ctx.stroke();

  // 转头时鼻子偏移体现
  const noseX = (rotateDeg / 30) * 12;
  ctx.fillStyle = '#ffab91';
  ctx.beginPath();
  ctx.ellipse(noseX, -20, 4, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#333';
  ctx.beginPath();
  if (rotateDeg > 0) {
    ctx.arc(4, -30, 3, 0, Math.PI * 2);
    ctx.arc(16, -30, 3, 0, Math.PI * 2);
  } else {
    ctx.arc(-4, -30, 3, 0, Math.PI * 2);
    ctx.arc(-16, -30, 3, 0, Math.PI * 2);
  }
  ctx.fill();

  // 旋转箭头
  const arrowR = 44;
  const startAngle = -Math.PI / 2 - 0.3;
  const endAngle = startAngle + (rotateDeg / 30) * 1.2;
  ctx.strokeStyle = rotateDeg > 0 ? '#e53935' : '#1e88e5';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(0, -28, arrowR, startAngle, endAngle, rotateDeg < 0);
  ctx.stroke();

  ctx.restore();
  ctx.restore();
}

function drawShrug(ctx, shrugPx) {
  const cx = WIDTH / 2;
  const cy = 200;

  ctx.save();
  ctx.translate(cx, cy + 10);

  // 躯干（不动）
  ctx.fillStyle = '#4fc3f7';
  ctx.beginPath();
  ctx.roundRect(-40, 210 - cy - 10, 80, 90, 10);
  ctx.fill();
  ctx.strokeStyle = '#0288d1';
  ctx.lineWidth = 2;
  ctx.stroke();

  // 肩膀（随耸肩上移）
  const shoulderY = -shrugPx;
  ctx.fillStyle = '#4fc3f7';
  // 左肩
  ctx.beginPath();
  ctx.ellipse(-55, shoulderY, 20, 14, -0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#0288d1';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // 右肩
  ctx.beginPath();
  ctx.ellipse(55, shoulderY, 20, 14, 0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  // 颈部（随耸肩上移）
  ctx.fillStyle = '#ffcc80';
  ctx.beginPath();
  ctx.roundRect(-10, -20 + shoulderY, 20, 30, 4);
  ctx.fill();
  ctx.strokeStyle = '#e65100';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // 头部
  ctx.save();
  ctx.translate(0, shoulderY - 20);
  ctx.fillStyle = '#ffe0b2';
  ctx.beginPath();
  ctx.ellipse(0, -28, 28, 32, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#bf360c';
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = '#333';
  ctx.beginPath();
  ctx.arc(-9, -30, 3.5, 0, Math.PI * 2);
  ctx.arc(9, -30, 3.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#bf360c';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(0, -22, 7, 0.2, Math.PI - 0.2);
  ctx.stroke();
  ctx.restore();

  // 箭头提示
  if (shrugPx > 5) {
    drawArrow(ctx, -55, 10, -55, -shrugPx - 10, '#43a047');
    drawArrow(ctx, 55, 10, 55, -shrugPx - 10, '#43a047');
  }

  ctx.restore();
}

function drawArrow(ctx, x1, y1, x2, y2, color) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const headLen = 10;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

// 生成GIF
async function makeGif() {
  const canvas = createCanvas(WIDTH, HEIGHT);
  const ctx = canvas.getContext('2d');

  const encoder = new GIFEncoder(WIDTH, HEIGHT, 'neuquant', true);
  // 15秒 = 总帧数 约75帧（每帧200ms），每个动作约均分
  encoder.setDelay(200);
  encoder.setRepeat(0);
  encoder.setQuality(10);
  encoder.start();

  for (const action of actions) {
    for (let f = 0; f < action.frames; f++) {
      const t = f / action.frames;
      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      drawBackground(ctx, action.name, action.desc);
      action.draw(ctx, t);
      encoder.addFrame(ctx);
    }
    // 停顿帧
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    drawBackground(ctx, action.name, action.desc);
    action.draw(ctx, 0);
    encoder.addFrame(ctx);
  }

  encoder.finish();

  const outputPath = path.join('C:\\Users\\Lenovo\\Desktop', 'cervical_health.gif');
  fs.writeFileSync(outputPath, encoder.out.getData());
  console.log('GIF已保存到：' + outputPath);
}

makeGif().catch(console.error);
