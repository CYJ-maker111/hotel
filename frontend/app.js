let selectedRoomId = null;
let currentView = "admin";

async function fetchJSON(url, options) {
    const res = await fetch(url, options);
    if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.message || `请求失败：${res.status}`);
    }
    return await res.json();
}

function stateBadge(state) {
    if (state === "serving") return '<span class="badge serving">送风</span>';
    if (state === "waiting") return '<span class="badge waiting">等待</span>';
    return '<span class="badge off">关机</span>';
}

// ---------- 管理员界面：房间列表 & 实时监控 ----------

async function loadRooms() {
    const rooms = await fetchJSON("/api/rooms");
    const tbody = document.querySelector("#rooms-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    rooms.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${r.room_id}</td>
            <td>${stateBadge(r.state)}</td>
            <td>${r.current_temp} ℃</td>
            <td>${r.mode}</td>
            <td>${r.fan_speed}</td>
            <td>${r.cost.toFixed(2)}</td>
            <td>-</td>
        `;
        tbody.appendChild(tr);
    });
}

// 管理员界面：加载房间下拉选择框
async function loadAdminRoomSelect() {
    const select = document.getElementById("admin-room-select");
    if (!select) return;
    const rooms = await fetchJSON("/api/rooms");
    select.innerHTML = "";
    rooms.forEach(r => {
        const opt = document.createElement("option");
        opt.value = r.room_id;
        opt.textContent = `房间 ${r.room_id}`;
        select.appendChild(opt);
    });
}

// 管理员界面：查看房间详单
async function adminViewRoomDetail() {
    const select = document.getElementById("admin-room-select");
    const roomId = parseInt(select.value);
    const container = document.getElementById("admin-detail");
    
    if (!roomId || !container) {
        alert("请先选择房间");
        return;
    }
    
    try {
        const detail = await fetchJSON(`/api/bills/${roomId}/detail`);
        
        // 更新表格
        let html = "";
        if (detail.records.length === 0) {
            html = "<p class='muted'>暂无使用记录</p>";
        } else {
            html = `
                <table style="width:100%; border-collapse: collapse; font-size:12px;">
                    <thead>
                        <tr>
                            <th>开始时间</th>
                            <th>结束时间</th>
                            <th>模式</th>
                            <th>目标温度</th>
                            <th>风速</th>
                            <th>费用(元)</th>
                            <th>操作类型</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            detail.records.forEach(record => {
                html += `
                    <tr>
                        <td>${record.start_time}</td>
                        <td>${record.end_time || '-'}</td>
                        <td>${record.mode}</td>
                        <td>${record.target_temp}°C</td>
                        <td>${record.fan_speed}</td>
                        <td>${record.cost.toFixed(2)}</td>
                        <td>${record.operation_type}</td>
                    </tr>
                `;
            });
            
            html += "</tbody></table>";
        }
        
        container.innerHTML = html;
        
    } catch (error) {
        container.innerHTML = `<p class='error'>获取详单失败：${error.message}</p>`;
    }
}

// 加载队列状态
async function loadQueues() {
    const servedQueue = await fetchJSON("/api/queues/served");
    const waitingQueue = await fetchJSON("/api/queues/waiting");
    
    // 更新服务队列
    const servedDiv = document.getElementById("served-queue");
    if (servedDiv) {
        const servedRooms = servedQueue.served_rooms.length > 0 ? 
            servedQueue.served_rooms.join(', ') : '无';
        servedDiv.innerHTML = `<p><strong>当前服务中的房间：</strong> ${servedRooms}</p>`;
    }
    
    // 更新等待队列
    const waitingDiv = document.getElementById("waiting-queue");
    if (waitingDiv) {
        const waitingRooms = waitingQueue.waiting_rooms.length > 0 ? 
            waitingQueue.waiting_rooms.join(', ') : '无';
        waitingDiv.innerHTML = `<p><strong>等待服务的房间：</strong> ${waitingRooms}</p>`;
    }
}



// ---------- 前台退房结账界面 ----------

// 标签切换功能
function initTabSwitch() {
    const checkinTab = document.getElementById("checkin-tab");
    const checkoutTab = document.getElementById("checkout-tab");
    const checkinSection = document.getElementById("checkin-section");
    const checkoutSection = document.getElementById("checkout-section");
    
    if (checkinTab && checkoutTab) {
        checkinTab.onclick = () => {
            checkinTab.classList.add("active");
            checkoutTab.classList.remove("active");
            checkinSection.style.display = "block";
            checkoutSection.style.display = "none";
        };
        
        checkoutTab.onclick = () => {
            checkoutTab.classList.add("active");
            checkinTab.classList.remove("active");
            checkoutSection.style.display = "block";
            checkinSection.style.display = "none";
        };
    }
}

// 登记入住相关函数
async function loadCheckinRooms() {
    const select = document.getElementById("ci-room-select");
    if (!select) return;
    const rooms = await fetchJSON("/api/rooms");
    select.innerHTML = "";
    rooms.forEach(r => {
        const opt = document.createElement("option");
        opt.value = r.room_id;
        opt.textContent = `房间 ${r.room_id}`;
        select.appendChild(opt);
    });
}

async function checkinRoom() {
    const select = document.getElementById("ci-room-select");
    const guestNameInput = document.getElementById("ci-guest-name");
    const checkinTimeInput = document.getElementById("ci-checkin-time");
    const checkoutTimeInput = document.getElementById("ci-checkout-time");
    const messageDiv = document.getElementById("ci-message");
    
    if (!select || !guestNameInput || !messageDiv) return;
    
    const roomId = parseInt(select.value, 10);
    const guestName = guestNameInput.value.trim();
    const checkinTime = checkinTimeInput.value;
    const checkoutTime = checkoutTimeInput.value;
    
    if (!roomId) {
        messageDiv.innerHTML = "<p class='error'>请选择有效的房间号。</p>";
        return;
    }
    
    if (!guestName) {
        messageDiv.innerHTML = "<p class='error'>请输入客人姓名。</p>";
        return;
    }
    
    // 可以在这里添加更多验证逻辑
    
    try {
        // 发送登记入住请求
        const response = await fetchJSON(`/api/rooms/${roomId}/checkin`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                guest_name: guestName, 
                checkin_time: checkinTime, 
                checkout_time: checkoutTime 
            })
        });
        
        messageDiv.innerHTML = `<p class='success'>房间 ${roomId} 登记入住成功！客人：${guestName}</p>`;
        
        // 清空表单
        guestNameInput.value = "";
        checkinTimeInput.value = "";
        checkoutTimeInput.value = "";
        
    } catch (error) {
        messageDiv.innerHTML = `<p class='error'>登记入住失败：${error.message}</p>`;
    }
}

// 结账相关函数
async function loadCheckoutRooms() {
    const select = document.getElementById("co-room-select");
    if (!select) return;
    const rooms = await fetchJSON("/api/rooms");
    select.innerHTML = "";
    rooms.forEach(r => {
        const opt = document.createElement("option");
        opt.value = r.room_id;
        opt.textContent = `房间 ${r.room_id}`;
        select.appendChild(opt);
    });
}

// 查看详单相关函数
async function viewRoomDetail() {
    const select = document.getElementById("co-room-select");
    const roomId = parseInt(select.value);
    if (!roomId) {
        alert("请先选择房间");
        return;
    }
    
    try {
        const detail = await fetchJSON(`/api/bills/${roomId}/detail`);
        
        // 更新表格
        const tbody = document.getElementById("detail-table").querySelector("tbody");
        tbody.innerHTML = "";
        
        if (detail.records.length === 0) {
            tbody.innerHTML = "<tr><td colspan='8' class='muted'>暂无使用记录</td></tr>";
        } else {
            detail.records.forEach(record => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${record.start_time}</td>
                    <td>${record.end_time || '-'}</td>
                    <td>${record.mode}</td>
                    <td>${record.target_temp}°C</td>
                    <td>${record.fan_speed}</td>
                    <td>${record.cost.toFixed(2)}</td>
                    <td>${record.operation_type}</td>
                `;
                tbody.appendChild(tr);
            });
        }
        
        // 显示详单区域
        document.getElementById("co-detail").style.display = "block";
        
    } catch (error) {
        alert("获取详单失败: " + error.message);
    }
}

async function loadCheckoutBill() {
    const select = document.getElementById("co-room-select");
    const container = document.getElementById("co-bill");
    if (!select || !container) return;
    const roomId = parseInt(select.value, 10);
    if (!roomId) {
        container.innerHTML = "<p class='muted'>请选择有效的房间号。</p>";
        return;
    }
    const bill = await fetchJSON(`/api/rooms/${roomId}/bill`);
    let html = `<p><b>房间：</b>${bill.room_id}</p>`;
    html += `<p><b>总费用：</b>${bill.total_cost} 元</p>`;
    html += "<table><tr><th>ID</th><th>开始时间</th><th>结束时间</th><th>模式</th><th>目标温度</th><th>风速</th><th>费率</th><th>费用</th><th>类型</th></tr>";
    bill.details.forEach(d => {
        html += `<tr>
            <td>${d.id}</td>
            <td>${d.start_time}</td>
            <td>${d.end_time || ""}</td>
            <td>${d.mode}</td>
            <td>${d.target_temp}</td>
            <td>${d.fan_speed}</td>
            <td>${d.fee_rate}</td>
            <td>${d.cost.toFixed(2)}</td>
            <td>${d.operation_type}</td>
        </tr>`;
    });
    html += "</table>";
    container.innerHTML = html;
}

async function checkoutRoom() {
    const select = document.getElementById("co-room-select");
    const container = document.getElementById("co-bill");
    
    if (!select || !container) return;
    
    const roomId = parseInt(select.value, 10);
    if (!roomId) {
        container.innerHTML = "<p class='error'>请选择有效的房间号。</p>";
        return;
    }
    
    try {
        // 发送结账请求
        const response = await fetchJSON(`/api/rooms/${roomId}/checkout`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        
        container.innerHTML = `<p class='success'>${response.message}</p>`;
        
        // 刷新房间列表和账单
        loadCheckoutRooms();
        
    } catch (error) {
        container.innerHTML = `<p class='error'>结账失败：${error.message}</p>`;
    }
}

function initFrontdeskView() {
    // 初始化标签切换
    initTabSwitch();
    
    // 登记入住部分
    const ciRefreshBtn = document.getElementById("ci-refresh-rooms");
    const checkinBtn = document.getElementById("ci-checkin-btn");
    if (ciRefreshBtn) {
        ciRefreshBtn.onclick = () => loadCheckinRooms();
    }
    if (checkinBtn) {
        checkinBtn.onclick = () => checkinRoom();
    }
    
    // 结账部分
    const coRefreshBtn = document.getElementById("co-refresh-rooms");
    const loadBillBtn = document.getElementById("co-load-bill");
    const viewDetailBtn = document.getElementById("co-view-detail");
    const checkoutBtn = document.getElementById("co-checkout");
    const printBtn = document.getElementById("co-print");
    if (coRefreshBtn) {
        coRefreshBtn.onclick = () => loadCheckoutRooms();
    }
    if (loadBillBtn) {
        loadBillBtn.onclick = () => loadCheckoutBill();
    }
    if (viewDetailBtn) {
        viewDetailBtn.onclick = () => viewRoomDetail();
    }
    if (checkoutBtn) {
        checkoutBtn.onclick = () => checkoutRoom();
    }
    if (printBtn) {
        printBtn.onclick = () => window.print();
    }
    
    // 初始加载数据
    loadCheckinRooms();
    loadCheckoutRooms();
}

// ---------- 经理报表界面 ----------

async function loadManagerReport() {
    const startInput = document.getElementById("mgr-start");
    const endInput = document.getElementById("mgr-end");
    const container = document.getElementById("mgr-result");
    if (!container) return;

    let start = startInput && startInput.value ? startInput.value.replace("T", " ") + ":00" : "";
    let end = endInput && endInput.value ? endInput.value.replace("T", " ") + ":00" : "";

    const params = new URLSearchParams();
    if (start) params.append("start", start);
    if (end) params.append("end", end);

    const url = "/api/report/summary_range" + (params.toString() ? `?${params.toString()}` : "");
    const data = await fetchJSON(url);

    const displayStart = data.start || "最早记录";
    const displayEnd = data.end || "最新记录";

    container.innerHTML = `
        <p><b>统计时间范围：</b>${displayStart} ~ ${displayEnd}</p>
        <p><b>总费用：</b>${data.total_cost.toFixed(2)} 元</p>
    `;
}

function initManagerView() {
    const btn = document.getElementById("mgr-query");
    if (btn) {
        btn.onclick = () => loadManagerReport();
    }
}

// ---------- 顶部视图切换 ----------

function switchView(view) {
    currentView = view;
    const views = ["admin", "frontdesk", "manager"];
    views.forEach(v => {
        const sec = document.getElementById(`view-${v}`);
        const btn = document.getElementById(`nav-${v}`);
        if (sec) sec.style.display = v === view ? "" : "none";
        if (btn) btn.classList.toggle("active", v === view);
    });
}

async function init() {
    // 导航切换
    const navAdmin = document.getElementById("nav-admin");
    const navFrontdesk = document.getElementById("nav-frontdesk");
    const navManager = document.getElementById("nav-manager");
    if (navAdmin) navAdmin.onclick = () => switchView("admin");
    if (navFrontdesk) navFrontdesk.onclick = () => switchView("frontdesk");
    if (navManager) navManager.onclick = () => switchView("manager");

    // 管理员界面初始化
    await loadRooms();
    await loadAdminRoomSelect();
    await loadQueues(); // 加载队列信息
    
    // 查看详单按钮
    const viewDetailBtn = document.getElementById("admin-view-detail");
    if (viewDetailBtn) {
        viewDetailBtn.onclick = () => adminViewRoomDetail();
    }
    
    // 模拟前进按钮
    const tickBtn = document.getElementById("tick-btn");
    if (tickBtn) {
        tickBtn.onclick = async () => {
            await fetchJSON("/api/tick", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({seconds: 60})
            });
            await loadRooms();
            await loadQueues(); // 更新队列信息
        };
    }

    // 前台、经理界面初始化
    initFrontdeskView();
    initManagerView();
}

window.addEventListener("load", init);

