// src/injectDev.js
(function() {
  'use strict';

  // 确保在 Binance 页面上运行
  if (!window.location.href.includes('binance.com')) return;

  // 创建容器
  const container = document.createElement('div');
  container.id = 'binance-trading-app';
  document.body.appendChild(container);

  // 加载开发脚本
  const script = document.createElement('script');
  script.src = 'http://127.0.0.1:3000/src/main.js';
  script.type = 'module';
  document.body.appendChild(script);
})();