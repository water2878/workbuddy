/* 合同审批页面 - 主逻辑 v2.1（含汇总+全状态编辑 + CDN容错 + 分页） */
const API_BASE = "";
const API_TOKEN = "{{API_TOKEN}}";
let editingContractId = null;
let editingProducts = [];
let editingContractStatus = "";

// 分页状态
let currentPage = 1;
let pageSize = 10;
let totalPages = 1;
let paginationData = null;

// CDN容错：PDF.js可能在国内加载失败，不能阻塞主流程
if (typeof pdfjsLib !== "undefined") {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.bootcdn.net/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
} else {
  console.warn("[合同] PDF.js CDN未加载，预览功能不可用");
}

async function apiFetch(url, options = {}) {
  options.headers = { ...options.headers, "Authorization": "Bearer " + API_TOKEN };
  return fetch(API_BASE + url, options);
}

// ── Tab切换 ──
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  if (tab === 'list') {
    document.querySelectorAll('.tab-btn')[0].classList.add('active');
    document.getElementById('tab-list').classList.add('active');
  } else {
    document.querySelectorAll('.tab-btn')[1].classList.add('active');
    document.getElementById('tab-summary').classList.add('active');
    loadSummary();
  }
}

// ── 自定义弹窗 ──
let _dialogResolve = null;
function showDialog({title, msg, type, placeholder, okText, okColor}) {
  return new Promise(resolve => {
    _dialogResolve = resolve;
    const overlay = document.getElementById("dialogOverlay");
    const inputWrap = document.getElementById("dialogInputWrap");
    const input = document.getElementById("dialogInput");
    const cancelBtn = document.getElementById("dialogCancel");
    const okBtn = document.getElementById("dialogOk");
    document.getElementById("dialogTitle").textContent = title || "提示";
    document.getElementById("dialogMsg").textContent = msg;
    if (type === "prompt") {
      inputWrap.style.display = "block";
      input.value = "";
      input.placeholder = placeholder || "";
    } else {
      inputWrap.style.display = "none";
    }
    if (type === "alert") {
      cancelBtn.style.display = "none";
    } else {
      cancelBtn.style.display = "";
    }
    okBtn.textContent = okText || "确定";
    if (okColor) okBtn.style.background = okColor;
    else okBtn.style.background = "";
    overlay.classList.add("active");
    if (type === "prompt") setTimeout(() => input.focus(), 100);
  });
}
function closeDialog(ok) {
  const overlay = document.getElementById("dialogOverlay");
  overlay.classList.remove("active");
  if (_dialogResolve) {
    const input = document.getElementById("dialogInput");
    const type = document.getElementById("dialogInputWrap").style.display !== "none" ? "prompt" : "";
    _dialogResolve(ok && type === "prompt" ? input.value : ok);
    _dialogResolve = null;
  }
}
function customConfirm(msg, title) { return showDialog({title: title || "确认", msg, type: "confirm"}); }
function customPrompt(msg, placeholder) { return showDialog({title: "输入", msg, type: "prompt", placeholder}); }
function customAlert(msg, title) { return showDialog({title: title || "提示", msg, type: "alert"}); }

// 切换页码
function changePage(delta) {
  const newPage = currentPage + delta;
  if (newPage >= 1 && newPage <= totalPages) {
    currentPage = newPage;
    loadContracts();
  }
}

// 切换每页条数
function changePageSize() {
  const select = document.getElementById("pageSize");
  if (select) {
    pageSize = parseInt(select.value);
    currentPage = 1;
    loadContracts();
  }
}

// 重置页码并加载合同列表（用于筛选条件变化时）
function resetPageAndLoad() {
  currentPage = 1;
  loadContracts();
}

// 切换状态筛选（现在通过下拉框触发，此函数保留用于兼容）
function switchStatus(status) {
  // 更新下拉框值
  const statusFilter = document.getElementById('statusFilter');
  if (statusFilter) {
    statusFilter.value = status;
  }
  
  // 重置页码并加载
  currentPage = 1;
  loadContracts();
}

// 防抖搜索
let searchTimeout = null;
function debounceSearch() {
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  searchTimeout = setTimeout(() => {
    currentPage = 1;
    loadContracts();
  }, 300); // 300ms 防抖
}

// 更新分页控件
function updatePagination(pagination) {
  const paginationEl = document.getElementById("pagination");
  if (!paginationEl) return;
  
  if (!pagination || pagination.total === 0) {
    paginationEl.style.display = "none";
    return;
  }
  
  paginationEl.style.display = "flex";
  document.getElementById("currentPage").textContent = pagination.page;
  document.getElementById("totalPages").textContent = pagination.total_pages;
  document.getElementById("totalCount").textContent = pagination.total;
  
  // 更新按钮状态
  document.getElementById("btnPrev").disabled = pagination.page <= 1;
  document.getElementById("btnNext").disabled = pagination.page >= pagination.total_pages;
}

async function loadContracts() {
  try {
    const status = document.getElementById("statusFilter").value;
    const dateFrom = document.getElementById("dateFrom").value;
    const dateTo = document.getElementById("dateTo").value;
    const searchInput = document.getElementById("searchInput");
    const searchKeyword = searchInput ? searchInput.value.trim() : "";
    let url = `/api/contracts/list?status=${status}&page=${currentPage}&page_size=${pageSize}`;
    if (dateFrom) url += "&from=" + dateFrom;
    if (dateTo) url += "&to=" + dateTo;
    if (searchKeyword) url += "&search=" + encodeURIComponent(searchKeyword);
    const res = await apiFetch(url);
    if (!res.ok) {
      document.getElementById("container").innerHTML = '<div class="empty"><p>API错误: ' + res.status + '</p></div>';
      return;
    }
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch(e) {
      document.getElementById("container").innerHTML = '<div class="empty"><p>JSON解析失败</p></div>';
      return;
    }
    const container = document.getElementById("container");
    
    // 更新分页数据（后端返回平铺字段，需要转换为 pagination 对象）
    paginationData = {
      page: data.page || 1,
      page_size: data.page_size || 10,
      total: data.total || 0,
      total_pages: data.total_pages || 1
    };
    totalPages = paginationData.total_pages;
    updatePagination(paginationData);
    
    // 显示总数
    const totalCount = data.total || data.count || 0;
    document.getElementById("count").textContent = totalCount;

    const statusLabels = {pending:"待审批", approved:"已通过", sent:"已发送", rejected:"已拒绝", draft:"草稿"};
    const statusClass = {pending:"warning", approved:"success", sent:"info", rejected:"danger", draft:""};
    const emptyIcons = {pending:"📭", approved:"✅", sent:"📤", rejected:"❌", all:"📋"};

    let html = '';
    if (!data.count) {
      html = `<div class="empty"><div class="empty-icon">${emptyIcons[status]||"📋"}</div><p>暂无${statusLabels[status]||""}合同</p></div>`;
    } else {
      html = data.contracts.map(c => {
        const st = c.status || status;
        const stLabel = statusLabels[st] || st;
        const stClass = statusClass[st] || "";
        const canApprove = st === "pending";
        const canEdit = true; // 全状态可编辑
        // 修订记录
        let revisionsHtml = "";
        if (c.revisions && c.revisions.length > 0) {
          revisionsHtml = `<div class="revisions"><h5>📝 修订记录</h5>` +
            c.revisions.map(r => `<div class="revision-item">${r.at} ${r.by}：${r.changes}${r.reason ? '（'+r.reason+'）' : ''}</div>`).join("") +
            `</div>`;
        }
        return `
      <div class="card" id="card-${c.id}">
        <div class="card-header">
          <span class="customer">${c.customer}</span>
          <span class="order-no">${c.order_no || "无单号"}</span>
          <span class="status-badge ${stClass}">${stLabel}</span>
          ${c.revisions && c.revisions.length > 0 ? '<span class="revision-tag">已修订</span>' : ''}
        </div>
        <div class="card-body">
          <div class="info-row">
            <div class="info-item"><label>公司名称</label><span>${c.customer_name || "未提供"}</span></div>
            <div class="info-item"><label>联系人</label><span>${c.customer_contact || "未提供"}</span></div>
            <div class="info-item"><label>联系电话</label><span>${c.customer_phone || "未提供"}</span></div>
            <div class="info-item"><label>收货地址</label><span>${c.customer_address || "未提供"}</span></div>
            <div class="info-item"><label>付款方式</label><span>${c.payment_terms || "未指定"}</span></div>
            <div class="info-item"><label>创建时间</label><span>${c.created_at || ""}</span></div>
            <div class="info-item"><label>业务员</label><span>${c.agent_id || "未知"}</span></div>
          </div>
          ${c.approved_at ? `<div class="info-row">
            <div class="info-item"><label>审批时间</label><span>${c.approved_at}</span></div>
            <div class="info-item"><label>审批人</label><span>${c.approved_by || ""}</span></div>
            ${c.sent_at ? `<div class="info-item"><label>发送时间</label><span>${c.sent_at}</span></div>` : ""}
          </div>` : ""}
          ${c.notes ? `<div class="info-row"><div class="info-item notes"><label>备注</label><span>${c.notes}</span></div></div>` : ""}
          ${c.reject_reason ? `<div class="info-row"><div class="info-item reject-reason"><label>拒绝原因</label><span>${c.reject_reason}</span></div></div>` : ""}
          ${revisionsHtml}
          <div class="products">
            <h4>产品清单</h4>
            ${(c.products || []).map(p => `<div class="product-item"><span>${p}</span><span>${p.includes("×") ? "" : "×1"}</span></div>`).join("")}
          </div>
          <div class="total">
            <span class="total-label">合同总额</span>
            <span class="total-amount">¥${(c.total_amount || 0).toLocaleString()}</span>
          </div>
        </div>
        <div class="card-footer">
          <button class="btn btn-preview" onclick="togglePdf('${c.id}')">查看 PDF</button>
          ${canEdit ? `<button class="btn btn-edit" onclick="openEdit('${c.id}')">编辑合同</button>` : ""}
          ${canApprove ? `
          <button class="btn btn-approve" onclick="approveContract('${c.id}')">批准</button>
          <button class="btn btn-reject" onclick="rejectContract('${c.id}')">拒绝</button>` : ""}
        </div>
        <div class="status" id="status-${c.id}"></div>
        <div class="pdf-viewer" id="pdf-${c.id}">
          <div class="pdf-toolbar">
            <button onclick="pdfPrev('${c.id}')" id="pdf-prev-${c.id}" disabled>&#9664;</button>
            <span id="pdf-page-${c.id}">0/0</span>
            <button onclick="pdfNext('${c.id}')" id="pdf-next-${c.id}" disabled>&#9654;</button>
            <button onclick="pdfZoom('${c.id}',-0.2)">-</button>
            <span class="zoom-info" id="pdf-zoom-${c.id}">100%</span>
            <button onclick="pdfZoom('${c.id}',0.2)">+</button>
            <button onclick="pdfZoom('${c.id}','fit')">适应</button>
          </div>
          <div class="pdf-canvas-wrap" id="pdf-wrap-${c.id}">
            <canvas id="pdf-canvas-${c.id}"></canvas>
          </div>
        </div>
      </div>
    `;
  }).join("");
    }

    if (container.getAttribute("data-hash") !== html) {
      container.innerHTML = html;
      container.setAttribute("data-hash", html);
    }

    if (window._highlightId) {
      const hid = window._highlightId;
      delete window._highlightId;
      setTimeout(() => {
        const card = document.getElementById('card-' + hid);
        if (card) {
          card.scrollIntoView({ behavior: 'smooth', block: 'center' });
          card.classList.add('highlight');
        }
      }, 300);
    }
  } catch (e) { console.error(e); }
}

// ========== 汇总统计 ==========
async function loadSummary() {
  try {
    const dateFrom = document.getElementById("dateFrom").value;
    const dateTo = document.getElementById("dateTo").value;
    let url = "/api/contracts/summary?status=all";
    if (dateFrom) url += "&from=" + dateFrom;
    if (dateTo) url += "&to=" + dateTo;
    const res = await apiFetch(url);
    const data = await res.json();
    if (data.status !== "ok") { customAlert("加载汇总失败"); return; }
    const s = data.summary;
    const statusLabels = {pending:"待审批", approved:"已通过", sent:"已发送", rejected:"已拒绝", draft:"草稿"};

    // 统计卡片
    const pendingCount = s.by_status.pending || 0;
    const approvedCount = (s.by_status.approved || 0) + (s.by_status.sent || 0);
    const rejectedCount = s.by_status.rejected || 0;

    let html = `
    <div class="summary-cards">
      <div class="summary-card sc-blue">
        <div class="sc-label">合同总数</div>
        <div class="sc-value">${s.total_count}</div>
        <div class="sc-sub">总金额 ¥${(s.total_amount||0).toLocaleString()}</div>
      </div>
      <div class="summary-card sc-orange">
        <div class="sc-label">待审批</div>
        <div class="sc-value">${pendingCount}</div>
      </div>
      <div class="summary-card sc-green">
        <div class="sc-label">已通过+已发送</div>
        <div class="sc-value">${approvedCount}</div>
      </div>
      <div class="summary-card sc-red">
        <div class="sc-label">已拒绝</div>
        <div class="sc-value">${rejectedCount}</div>
      </div>
    </div>`;

    // 月度趋势图
    if (s.by_month && s.by_month.length > 0) {
      const maxAmount = Math.max(...s.by_month.map(m => m.amount), 1);
      const months = [...s.by_month].reverse(); // 时间正序
      html += `<div class="summary-section"><h3>📈 月度趋势</h3>
        <div class="chart-bar-row">`;
      months.forEach(m => {
        const h = Math.max(5, (m.amount / maxAmount) * 140);
        html += `<div style="flex:1;text-align:center">
          <div class="chart-bar" style="height:${h}px" title="${m.month}: ¥${m.amount.toLocaleString()} (${m.count}份)">
            <div class="chart-bar-val">¥${(m.amount/10000).toFixed(1)}万</div>
          </div>
          <div class="chart-bar-label">${m.month.slice(5)}</div>
        </div>`;
      });
      html += `</div></div>`;
    }

    // 客户维度
    if (s.by_customer && s.by_customer.length > 0) {
      html += `<div class="summary-section"><h3>🏢 客户汇总</h3>
        <table class="summary-table">
          <tr><th>客户</th><th>合同数</th><th>总金额</th><th>最近合同</th></tr>`;
      s.by_customer.forEach(c => {
        html += `<tr>
          <td>${c.name}</td>
          <td><span class="count-badge">${c.count}</span></td>
          <td class="amount">¥${c.amount.toLocaleString()}</td>
          <td>${c.latest || ""}</td>
        </tr>`;
      });
      html += `</table></div>`;
    }

    // 产品维度
    if (s.by_product && s.by_product.length > 0) {
      html += `<div class="summary-section"><h3>📦 产品汇总</h3>
        <table class="summary-table">
          <tr><th>型号</th><th>总数量</th><th>总金额</th><th>涉及合同</th></tr>`;
      s.by_product.forEach(p => {
        html += `<tr>
          <td>${p.model}</td>
          <td>${p.count}</td>
          <td class="amount">¥${p.amount.toLocaleString()}</td>
          <td><span class="count-badge">${p.contracts}</span></td>
        </tr>`;
      });
      html += `</table></div>`;
    }

    document.getElementById("summaryContainer").innerHTML = html;
  } catch (e) {
    console.error(e);
    document.getElementById("summaryContainer").innerHTML = '<div class="empty"><p>加载汇总失败</p></div>';
  }
}

// ========== PDF 预览 ==========
const _pdfState = {};

function togglePdf(id, _retryCount) {
  if (typeof pdfjsLib === 'undefined') { customAlert('PDF.js 加载失败，请刷新页面重试'); return; }
  const viewer = document.getElementById("pdf-" + id);
  const btn = document.querySelector(`#card-${id} .btn-preview`);
  if (!viewer) return;
  if (viewer.classList.contains("active")) {
    viewer.classList.remove("active");
    if (btn) btn.textContent = "查看 PDF";
    return;
  }
  viewer.classList.add("active");
  if (btn) btn.textContent = "收起预览";
  // 清除旧状态，始终重新加载（确保编辑后拿到最新PDF）
  delete _pdfState[id];
  _pdfState[id] = { doc: null, page: 1, zoom: 1.0, dragging: false, lastX: 0, lastY: 0 };
  const retryCount = _retryCount || 0;
  const wrap = document.getElementById("pdf-wrap-" + id);
  if (wrap) wrap.innerHTML = '<div class="pdf-loading" id="pdf-loading-' + id + '" style="padding:40px;text-align:center;color:#718096;"><p>PDF加载中...</p></div><canvas id="pdf-canvas-' + id + '" style="display:none"></canvas>';
  pdfjsLib.getDocument("/api/contracts/pdf/" + id + "?t=" + Date.now()).promise.then(doc => {
    _pdfState[id].doc = doc;
    _pdfState[id].page = 1;
    // 隐藏加载提示，显示canvas
    const loadingEl = document.getElementById("pdf-loading-" + id);
    if (loadingEl) loadingEl.style.display = "none";
    const canvasEl = document.getElementById("pdf-canvas-" + id);
    if (canvasEl) canvasEl.style.display = "";
    _renderPage(id, true);
    wrap.onmousedown = e => { _pdfState[id].dragging = true; _pdfState[id].lastX = e.clientX; _pdfState[id].lastY = e.clientY; };
    wrap.onmousemove = e => { if (!_pdfState[id].dragging) return; wrap.scrollLeft -= e.clientX - _pdfState[id].lastX; wrap.scrollTop -= e.clientY - _pdfState[id].lastY; _pdfState[id].lastX = e.clientX; _pdfState[id].lastY = e.clientY; };
    wrap.onmouseup = () => { _pdfState[id].dragging = false; };
    wrap.onmouseleave = () => { _pdfState[id].dragging = false; };
  }).catch(e => {
    console.error("PDF load error:", e);
    if (retryCount < 3) {
      // PDF可能还在异步生成中，自动重试
      const wrap2 = document.getElementById("pdf-wrap-" + id);
      if (wrap2) wrap2.innerHTML = `<div class="pdf-loading" id="pdf-loading-${id}" style="padding:40px;text-align:center;color:#718096;"><p>PDF正在生成中，${(retryCount+1)*2}秒后自动重试 (${retryCount+1}/3)...</p></div><canvas id="pdf-canvas-${id}" style="display:none"></canvas>`;
      setTimeout(() => togglePdf(id, retryCount + 1), (retryCount + 1) * 2000);
    } else {
      const wrap3 = document.getElementById("pdf-wrap-" + id);
      if (wrap3) wrap3.innerHTML = '<div style="padding:40px;text-align:center;color:#e53e3e;"><p style="font-size:16px;margin-bottom:8px;">⚠️ PDF加载失败</p><p style="font-size:13px;color:#666;">可能原因：PDF尚未生成完成，或服务器生成失败</p><p style="font-size:12px;color:#999;margin-top:12px;">'+(e.message||"未知错误")+'</p><button onclick="togglePdf(\''+id+'\')" style="margin-top:16px;padding:6px 20px;background:#3182ce;color:#fff;border:none;border-radius:4px;cursor:pointer;">重试</button></div>';
    }
  });
}

function _renderPage(id, autoFit) {
  const s = _pdfState[id]; if (!s || !s.doc) return;
  s.doc.getPage(s.page).then(page => {
    if (autoFit) {
      const wrap = document.getElementById("pdf-wrap-" + id);
      const baseViewport = page.getViewport({ scale: 1.0 });
      s.zoom = (wrap.clientWidth - 30) / baseViewport.width;
    }
    const dpr = window.devicePixelRatio || 1;
    const viewport = page.getViewport({ scale: s.zoom * dpr });
    const canvas = document.getElementById("pdf-canvas-" + id);
    const ctx = canvas.getContext("2d");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = (viewport.width / dpr) + "px";
    canvas.style.height = (viewport.height / dpr) + "px";
    page.render({ canvasContext: ctx, viewport: viewport });
    document.getElementById("pdf-page-" + id).textContent = s.page + "/" + s.doc.numPages;
    document.getElementById("pdf-zoom-" + id).textContent = Math.round(s.zoom * 100) + "%";
    document.getElementById("pdf-prev-" + id).disabled = s.page <= 1;
    document.getElementById("pdf-next-" + id).disabled = s.page >= s.doc.numPages;
  });
}

function pdfPrev(id) { const s = _pdfState[id]; if (s && s.page > 1) { s.page--; _renderPage(id); } }
function pdfNext(id) { const s = _pdfState[id]; if (s && s.doc && s.page < s.doc.numPages) { s.page++; _renderPage(id); } }
function pdfZoom(id, delta) {
  const s = _pdfState[id]; if (!s) return;
  if (delta === "fit") { _renderPage(id, true); return; }
  s.zoom = Math.max(0.3, Math.min(4, s.zoom + delta));
  _renderPage(id);
}

// ========== 编辑合同（全状态可编辑）==========
async function openEdit(contractId) {
  editingContractId = contractId;
  try {
    const res = await apiFetch("/api/contracts/detail/" + contractId);
    const data = await res.json();
    if (data.status !== "ok") { customAlert("获取合同详情失败"); return; }
    const c = data.contract;
    const o = c.order;
    editingProducts = o.products || [];
    editingContractStatus = c.status;

    // 如果合同已审批/已发送，显示警告
    let warningHtml = "";
    if (c.status === "approved" || c.status === "sent") {
      warningHtml = `<div class="modify-warning">⚠️ 修改已审批/已发送的合同后，状态将回退为"待审批"，需要重新审批</div>`;
    }

    let productsHtml = editingProducts.map((p, i) => {
      const imgs = p.images || [];
      const imgsHtml = imgs.map((url, j) => `<div class="img-thumb" style="background-image:url(${url})"><button onclick="removeProductImg(${i},${j})">&times;</button></div>`).join("");
      return `
      <div class="product-edit" id="pedit-${i}">
        <button class="remove-product" onclick="removeProduct(${i})" title="删除产品">&times;</button>
        <div class="form-row">
          <div class="form-group"><label>型号</label><input id="p-model-${i}" value="${p.model || ''}"></div>
          <div class="form-group"><label>概述</label><input id="p-desc-${i}" value="${p.description || ''}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>台架尺寸</label><input id="p-frame-size-${i}" value="${p.frame_size || ''}"></div>
          <div class="form-group"><label>钢架颜色</label><input id="p-frame-color-${i}" value="${p.frame_color || ''}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>数量</label><input id="p-qty-${i}" type="number" min="1" value="${p.quantity || 1}"></div>
          <div class="form-group"><label>单价(元)</label><input id="p-price-${i}" type="number" min="0" value="${p.unit_price || 0}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>单体积(m³)</label><input id="p-volume-${i}" value="${p.unit_volume || ''}"></div>
          <div class="form-group"><label>单重量(KG)</label><input id="p-weight-${i}" value="${p.unit_weight || ''}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>小计</label><input id="p-subtotal-${i}" type="number" readonly value="${p.subtotal || 0}" style="background:#f0f0f0"></div>
          <div class="form-group"><label>备注</label><input id="p-remark-${i}" value="${p.remark || ''}"></div>
        </div>
        <div class="form-group">
          <label>产品图片</label>
          <div class="img-row" id="p-imgs-${i}">${imgsHtml}<label class="img-add" for="p-file-${i}">+</label><input type="file" id="p-file-${i}" accept="image/*" multiple onchange="onProductImgUpload(${i},this)" style="display:none"></div>
        </div>
      </div>`;
    }).join("");

    document.getElementById("editBody").innerHTML = `
      ${warningHtml}
      <div class="form-row">
        <div class="form-group"><label>客户/公司名</label><input id="e-customer-name" value="${o.customer_name || ''}"></div>
        <div class="form-group"><label>联系人</label><input id="e-customer-contact" value="${o.customer_contact || ''}"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>电话</label><input id="e-customer-phone" value="${o.customer_phone || ''}"></div>
        <div class="form-group"><label>收货地址</label><input id="e-customer-address" value="${o.customer_address || ''}"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>付款方式</label><input id="e-payment-terms" value="${o.payment_terms || ''}"></div>
        <div class="form-group"><label>收货国家</label><input id="e-shipping-country" value="${o.shipping_country || ''}"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>电压</label><input id="e-voltage" value="${o.voltage || ''}"></div>
        <div class="form-group"><label>插头类型</label><input id="e-plug-type" value="${o.plug_type || ''}"></div>
      </div>
      ${c.status === "approved" || c.status === "sent" ? `
      <div class="form-group">
        <label>修改原因 <span style="color:#e74c3c">*必填</span></label>
        <input id="e-reason" placeholder="请说明修改原因" required>
      </div>` : ''}
      <div class="form-group"><label>备注</label><textarea id="e-notes" rows="2">${o.notes || ''}</textarea></div>
      <h4 style="margin:15px 0 10px;color:#555">产品清单</h4>
      <div id="productsContainer">${productsHtml}</div>
      <button class="add-product-btn" onclick="addProduct()">+ 添加产品</button>
      <div class="batch-upload" style="margin-top:15px">
        <h4 style="margin:0 0 8px;color:#555">批量上传产品图片</h4>
        <p style="font-size:12px;color:#999;margin:0 0 8px">文件名含型号关键词即可自动匹配</p>
        <label class="add-product-btn" for="batch-img-upload" style="cursor:pointer">+ 选择图片（可多选）</label>
        <input type="file" id="batch-img-upload" accept="image/*" multiple onchange="onBatchImgUpload(this)" style="display:none">
        <div id="batch-upload-result" style="margin-top:8px;font-size:13px;color:#666"></div>
      </div>
    `;

    // 绑定自动计算小计
    setTimeout(() => {
      editingProducts.forEach((_, i) => {
        const qtyEl = document.getElementById("p-qty-" + i);
        const priceEl = document.getElementById("p-price-" + i);
        const subEl = document.getElementById("p-subtotal-" + i);
        if (qtyEl && priceEl) {
          const calcSub = () => { subEl.value = (parseInt(qtyEl.value)||0) * (parseFloat(priceEl.value)||0); };
          qtyEl.addEventListener("input", calcSub);
          priceEl.addEventListener("input", calcSub);
        }
      });
    }, 100);

    document.getElementById("editModal").classList.add("active");
  } catch (e) {
    customAlert("获取合同详情失败: " + e.message);
  }
}

function addProduct() {
  const i = editingProducts.length;
  editingProducts.push({ model: "", description: "", frame_size: "", frame_color: "", quantity: 1, unit_price: 0, unit_volume: "", unit_weight: "", subtotal: 0, remark: "", images: [] });
  const container = document.getElementById("productsContainer");
  const div = document.createElement("div");
  div.className = "product-edit";
  div.id = "pedit-" + i;
  div.innerHTML = `
    <button class="remove-product" onclick="removeProduct(${i})" title="删除产品">&times;</button>
    <div class="form-row">
      <div class="form-group"><label>型号</label><input id="p-model-${i}" value=""></div>
      <div class="form-group"><label>概述</label><input id="p-desc-${i}" value=""></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>台架尺寸</label><input id="p-frame-size-${i}" value=""></div>
      <div class="form-group"><label>钢架颜色</label><input id="p-frame-color-${i}" value=""></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>数量</label><input id="p-qty-${i}" type="number" min="1" value="1"></div>
      <div class="form-group"><label>单价(元)</label><input id="p-price-${i}" type="number" min="0" value="0"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>单体积(m³)</label><input id="p-volume-${i}" value=""></div>
      <div class="form-group"><label>单重量(KG)</label><input id="p-weight-${i}" value=""></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>小计</label><input id="p-subtotal-${i}" type="number" readonly value="0" style="background:#f0f0f0"></div>
      <div class="form-group"><label>备注</label><input id="p-remark-${i}" value=""></div>
    </div>
    <div class="form-group">
      <label>产品图片</label>
      <div class="img-row" id="p-imgs-${i}"><label class="img-add" for="p-file-${i}">+</label><input type="file" id="p-file-${i}" accept="image/*" multiple onchange="onProductImgUpload(${i},this)" style="display:none"></div>
    </div>
  `;
  container.appendChild(div);

  const qtyEl = document.getElementById("p-qty-" + i);
  const priceEl = document.getElementById("p-price-" + i);
  const subEl = document.getElementById("p-subtotal-" + i);
  const calcSub = () => { subEl.value = (parseInt(qtyEl.value)||0) * (parseFloat(priceEl.value)||0); };
  qtyEl.addEventListener("input", calcSub);
  priceEl.addEventListener("input", calcSub);
}

function removeProduct(index) {
  editingProducts.splice(index, 1);
  openEdit(editingContractId);
}

// ── 图片上传 ──
let _uploadCounter = {};
async function uploadImage(file) {
  const fd = new FormData();
  fd.append("image", file);
  fd.append("contract_id", editingContractId || "unknown");
  if (!_uploadCounter[editingContractId]) _uploadCounter[editingContractId] = 0;
  _uploadCounter[editingContractId]++;
  fd.append("seq", _uploadCounter[editingContractId]);
  const res = await apiFetch("/api/contracts/upload-image", { method: "POST", body: fd });
  const data = await res.json();
  if (data.status === "ok") return data.url;
  throw new Error(data.error || "上传失败");
}

async function onProductImgUpload(idx, input) {
  if (!input.files || !input.files.length) return;
  const files = Array.from(input.files);
  if (!editingProducts[idx].images) editingProducts[idx].images = [];
  for (const f of files) {
    try {
      const url = await uploadImage(f);
      editingProducts[idx].images.push(url);
    } catch (e) { customAlert("图片上传失败: " + e.message); }
  }
  const container = document.getElementById("p-imgs-" + idx);
  const addBtn = container.querySelector(".img-add");
  const addInput = container.querySelector("input[type=file]");
  container.innerHTML = "";
  editingProducts[idx].images.forEach((url, j) => {
    const d = document.createElement("div");
    d.className = "img-thumb";
    d.style.backgroundImage = `url(${url})`;
    d.innerHTML = `<button onclick="removeProductImg(${idx},${j})">&times;</button>`;
    container.appendChild(d);
  });
  container.appendChild(addBtn);
  container.appendChild(addInput);
  input.value = "";
}

function removeProductImg(idx, imgIdx) {
  if (editingProducts[idx].images) {
    editingProducts[idx].images.splice(imgIdx, 1);
    const container = document.getElementById("p-imgs-" + idx);
    const addBtn = container.querySelector(".img-add");
    const addInput = container.querySelector("input[type=file]");
    container.innerHTML = "";
    editingProducts[idx].images.forEach((url, j) => {
      const d = document.createElement("div");
      d.className = "img-thumb";
      d.style.backgroundImage = `url(${url})`;
      d.innerHTML = `<button onclick="removeProductImg(${idx},${j})">&times;</button>`;
      container.appendChild(d);
    });
    container.appendChild(addBtn);
    container.appendChild(addInput);
  }
}

async function onBatchImgUpload(input) {
  if (!input.files || !input.files.length) return;
  const files = Array.from(input.files);
  const resultDiv = document.getElementById("batch-upload-result");
  resultDiv.innerHTML = "上传中...";
  let matched = 0, unmatched = 0;
  for (const f of files) {
    try {
      const url = await uploadImage(f);
      const fname = f.name.toUpperCase();
      let found = false;
      for (let i = 0; i < editingProducts.length; i++) {
        const model = (editingProducts[i].model || "").trim().toUpperCase();
        if (model && fname.includes(model)) {
          if (!editingProducts[i].images) editingProducts[i].images = [];
          editingProducts[i].images.push(url);
          found = true;
          matched++;
          break;
        }
      }
      if (!found) unmatched++;
    } catch (e) { resultDiv.innerHTML += `<br>失败: ${f.name}`; }
  }
  resultDiv.innerHTML = `已上传 ${files.length} 张，匹配 ${matched} 张${unmatched > 0 ? "，未匹配 " + unmatched + " 张" : ""}`;
  openEdit(editingContractId);
  input.value = "";
}

function closeEdit() {
  document.getElementById("editModal").classList.remove("active");
  editingContractId = null;
  editingProducts = [];
  editingContractStatus = "";
}

async function saveEdit() {
  if (!editingContractId) return;
  // 已审批/已发送合同必须填修改原因
  if (editingContractStatus === "approved" || editingContractStatus === "sent") {
    const reason = (document.getElementById("e-reason") || {}).value || "";
    if (!reason) {
      customAlert("修改已审批合同必须填写修改原因");
      return;
    }
  }

  const saveBtn = document.getElementById("saveBtn");
  saveBtn.textContent = "生成中...";
  saveBtn.disabled = true;

  const products = editingProducts.map((_, i) => ({
    model: (document.getElementById("p-model-" + i) || {}).value || "",
    description: (document.getElementById("p-desc-" + i) || {}).value || "",
    frame_size: (document.getElementById("p-frame-size-" + i) || {}).value || "",
    frame_color: (document.getElementById("p-frame-color-" + i) || {}).value || "",
    quantity: parseInt((document.getElementById("p-qty-" + i) || {}).value) || 1,
    unit_price: parseFloat((document.getElementById("p-price-" + i) || {}).value) || 0,
    unit_volume: (document.getElementById("p-volume-" + i) || {}).value || "",
    unit_weight: (document.getElementById("p-weight-" + i) || {}).value || "",
    subtotal: parseInt((document.getElementById("p-qty-" + i) || {}).value || 0) * parseFloat((document.getElementById("p-price-" + i) || {}).value || 0),
    remark: (document.getElementById("p-remark-" + i) || {}).value || "",
    images: (editingProducts[i] || {}).images || []
  })).filter(p => p.model);

  const updates = {
    customer_name: (document.getElementById("e-customer-name") || {}).value || "",
    customer_contact: (document.getElementById("e-customer-contact") || {}).value || "",
    customer_phone: (document.getElementById("e-customer-phone") || {}).value || "",
    customer_address: (document.getElementById("e-customer-address") || {}).value || "",
    payment_terms: (document.getElementById("e-payment-terms") || {}).value || "",
    shipping_country: (document.getElementById("e-shipping-country") || {}).value || "",
    voltage: (document.getElementById("e-voltage") || {}).value || "",
    plug_type: (document.getElementById("e-plug-type") || {}).value || "",
    notes: (document.getElementById("e-notes") || {}).value || "",
    products: products,
    _reason: (document.getElementById("e-reason") || {}).value || ""
  };

  try {
    const res = await apiFetch("/api/contracts/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_id: editingContractId, updates: updates })
    });
    const data = await res.json();
    if (data.status === "ok") {
      const cid = editingContractId;
      // 清除旧PDF缓存，强制下次预览重新加载
      delete _pdfState[cid];
      closeEdit();
      loadContracts();
      const statusEl = document.getElementById("status-" + cid);
      if (statusEl) {
        statusEl.className = "status success";
        statusEl.textContent = data.needs_reapproval
          ? "合同已修改，需重新审批"
          : "合同已更新，PDF已重新生成";
        setTimeout(() => { statusEl.textContent = ""; }, 4000);
      }
    } else {
      customAlert("更新失败: " + (data.error || "未知错误"));
    }
  } catch (e) {
    customAlert("请求失败: " + e.message);
  } finally {
    saveBtn.textContent = "保存并重新生成";
    saveBtn.disabled = false;
  }
}

// ========== 审批操作 ==========
async function approveContract(id) {
  if (!await customConfirm("批准后将自动发送PDF给客户。", "确认批准该合同？")) return;
  const statusEl = document.getElementById("status-" + id);
  statusEl.className = "status";
  statusEl.textContent = "正在审批...";
  try {
    const res = await apiFetch("/api/contracts/approve", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ contract_id: id })
    });
    const data = await res.json();
    if (data.status === "ok") {
      statusEl.className = "status success";
      statusEl.textContent = "✅ 审批已通过！将通过SSE推送到本地发送...";
      // 本地Claw通过SSE订阅接收审批事件，无需前端直接调用
      setTimeout(() => loadContracts(), 1500);
    } else {
      statusEl.className = "status error";
      statusEl.textContent = "❌ 失败: " + (data.error || "未知错误");
    }
  } catch (e) {
    statusEl.className = "status error";
    statusEl.textContent = "❌ 请求失败: " + e.message;
  }
}

async function rejectContract(id) {
  if (!await customConfirm("拒绝后合同将退回，确认继续？", "确认拒绝该合同？")) return;
  const reason = await customPrompt("请输入拒绝原因（可选）:", "拒绝原因");
  const statusEl = document.getElementById("status-" + id);
  statusEl.className = "status";
  statusEl.textContent = "正在处理...";
  try {
    const res = await apiFetch("/api/contracts/reject", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ contract_id: id, reason: reason || "" })
    });
    const data = await res.json();
    if (data.status === "ok") {
      statusEl.className = "status error";
      statusEl.textContent = "❌ 已拒绝";
      setTimeout(() => loadContracts(), 1500);
    } else {
      statusEl.className = "status error";
      statusEl.textContent = "❌ 失败: " + (data.error || "未知错误");
    }
  } catch (e) {
    statusEl.className = "status error";
    statusEl.textContent = "❌ 请求失败: " + e.message;
  }
}

// ========== 初始化 ==========
(function() {
  const urlParams = new URLSearchParams(window.location.search);
  const highlightId = urlParams.get('id');
  if (highlightId) {
    document.getElementById("statusFilter").value = "all";
    window._highlightId = highlightId;
    window.history.replaceState({}, '', '/contracts');
  }
})();
// ═══════════════════════════════════════════════════════
// SSE 连接管理（支持断线重连和增量同步）
// ═══════════════════════════════════════════════════════
let evtSource = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let reconnectDelay = 1000; // 初始重连延迟1秒
let lastSyncTimestamp = 0; // 最后同步时间戳
let clientId = localStorage.getItem('sse_client_id') || generateClientId();

// 生成客户端ID
function generateClientId() {
  const id = 'client_' + Math.random().toString(36).substr(2, 9);
  localStorage.setItem('sse_client_id', id);
  return id;
}

// 初始化 SSE 连接
function initSSE() {
  if (evtSource) {
    evtSource.close();
  }
  
  // 构建连接URL（包含最后同步时间和客户端ID）
  let url = "/api/contracts/events";
  if (lastSyncTimestamp > 0) {
    url += `?last_sync=${lastSyncTimestamp}&client_id=${clientId}`;
  } else {
    url += `?client_id=${clientId}`;
  }
  
  console.log(`[SSE] 连接到: ${url}`);
  evtSource = new EventSource(url);
  
  // 连接成功
  evtSource.onopen = function() {
    console.log("[SSE] 连接已建立");
    reconnectAttempts = 0; // 重置重连次数
    reconnectDelay = 1000; // 重置重连延迟
  };
  
  // 处理消息
  evtSource.onmessage = function(e) {
    if (e.data === "update") {
      console.log("[SSE] 收到更新通知，刷新列表");
      loadContracts();
    }
  };
  
  // 处理特定事件
  evtSource.addEventListener('connected', function(e) {
    const data = JSON.parse(e.data);
    console.log(`[SSE] 连接成功，客户端ID: ${data.client_id}`);
    if (data.client_id) {
      clientId = data.client_id;
      localStorage.setItem('sse_client_id', clientId);
    }
  });
  
  // 处理追赶同步事件（断线重连后）
  evtSource.addEventListener('catch_up_sync', function(e) {
    const data = JSON.parse(e.data);
    console.log(`[SSE] 收到追赶同步: ${data.total} 条变更`);
    handleCatchUpSync(data.changes);
  });
  
  // 处理文件变更事件
  evtSource.addEventListener('file_change', function(e) {
    const data = JSON.parse(e.data);
    console.log(`[SSE] 文件变更: ${data.change_type} - ${data.file_path}`);
    // 更新最后同步时间
    lastSyncTimestamp = Date.now() / 1000;
    // 刷新相关数据
    if (data.file_path.includes('contracts')) {
      loadContracts();
    }
  });
  
  // 心跳事件
  evtSource.addEventListener('heartbeat', function(e) {
    // 收到心跳，更新最后活跃时间
    lastSyncTimestamp = Date.now() / 1000;
  });
  
  // 错误处理
  evtSource.onerror = function(e) {
    console.error("[SSE] 连接错误:", e);
    evtSource.close();
    
    // 尝试重连
    if (reconnectAttempts < maxReconnectAttempts) {
      reconnectAttempts++;
      const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttempts - 1), 30000); // 最大30秒
      console.log(`[SSE] ${delay/1000}秒后尝试第${reconnectAttempts}次重连...`);
      setTimeout(initSSE, delay);
    } else {
      console.warn("[SSE] 达到最大重连次数，切换到轮询模式");
      // 切换到轮询模式
      setInterval(loadContracts, 15000);
    }
  };
}

// 处理追赶同步
function handleCatchUpSync(changes) {
  if (!changes || changes.length === 0) return;
  
  console.log(`[SSE] 处理 ${changes.length} 条 missed 变更`);
  
  // 根据变更类型执行相应操作
  const contractChanges = changes.filter(c => c.file_path.includes('contracts'));
  const imageChanges = changes.filter(c => c.file_path.includes('images'));
  
  if (contractChanges.length > 0) {
    console.log(`[SSE] ${contractChanges.length} 条合同变更，刷新列表`);
    loadContracts();
  }
  
  if (imageChanges.length > 0) {
    console.log(`[SSE] ${imageChanges.length} 条图片变更`);
    // 可以在这里刷新图片缓存
  }
  
  // 更新最后同步时间
  lastSyncTimestamp = Date.now() / 1000;
}

// 启动 SSE 连接
initSSE();

// 页面可见性变化时处理连接
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
      // 页面隐藏时，记录时间但不关闭连接
      console.log("[SSE] 页面隐藏，保持连接");
    } else {
      // 页面显示时，检查连接状态
      if (evtSource.readyState === EventSource.CLOSED) {
        console.log("[SSE] 页面显示，重新连接");
        initSSE();
      }
    }
  });
}
