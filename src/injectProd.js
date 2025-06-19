// src/injectProd.js
(function() {
  'use strict';

  // 确保在 Binance 页面上运行
  if (!window.location.href.includes('binance.com')) return;

  // 创建容器
  const container = document.createElement('div');
  container.id = 'binance-trading-app';
  document.body.appendChild(container);

  // 注入主要脚本（这里应该是打包后的脚本）
  const script = document.createElement('script');
  script.src = 'path/to/your/bundled/main.js';
  script.type = 'module';
  document.body.appendChild(script);
})();