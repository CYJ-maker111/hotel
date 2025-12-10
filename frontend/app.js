let selectedRoomId = null;
let currentView = "admin";

// 测试相关全局变量
let testRunning = false;
let testPaused = false;
let currentTestMinute = 0;
let totalTestMinutes = 0;
let testSimulationInterval = null;
let initialTemperatures = {};
let defaultWindSpeed = "MEDIUM";

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
    if (state === "paused") return '<span class="badge paused">暂停</span>';
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
            <td>${r.target_temp} ℃</td>
            <td>${r.mode}</td>
            <td>${r.fan_speed}</td>
            <td>${r.cost.toFixed(2)}</td>
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
async function adminResetRoomCost() {
    const select = document.getElementById("admin-room-select");
    const roomId = parseInt(select.value);
    
    if (!roomId) {
        alert("请先选择房间");
        return;
    }
    
    if (!confirm(`确定要重置房间${roomId}的累计费用吗？\n这将清空该房间的所有详单记录！`)) {
        return;
    }
    
    try {
        const result = await fetchJSON(`/api/bills/${roomId}/reset`, {
            method: 'POST'
        });
        
        if (result.status === 'success') {
            alert(`${result.message}\n已删除 ${result.deleted_records} 条记录`);
            // 刷新详单显示
            await adminViewRoomDetail();
            // 刷新房间列表
            await loadRoomsStatus();
        } else {
            alert(`重置失败：${result.message}`);
        }
    } catch (error) {
        alert(`重置失败：${error.message}`);
    }
}

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
                            <th>请求时间</th>
                            <th>开始时间</th>
                            <th>结束时间</th>
                            <th>时长(秒)</th>
                            <th>风速</th>
                            <th>当前费用</th>
                            <th>累积费用</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            detail.records.forEach(record => {
                html += `
                    <tr>
                        <td>${record.request_time || '-'}</td>
                        <td>${record.start_time}</td>
                        <td>${record.end_time || '-'}</td>
                        <td>${record.service_duration || 0}</td>
                        <td>${record.fan_speed}</td>
                        <td>${record.cost.toFixed(2)}</td>
                        <td>${record.accumulated_cost.toFixed(2)}</td>
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
        messageDiv.innerHTML = "<p style='color:#dc2626;'>⚠️ 请选择有效的房间号。</p>";
        return;
    }
    
    if (!guestName) {
        messageDiv.innerHTML = "<p style='color:#dc2626;'>⚠️ 请输入客人姓名。</p>";
        return;
    }
    
    // 强制验证入住时间
    if (!checkinTime) {
        messageDiv.innerHTML = "<p style='color:#dc2626;'>⚠️ 请填写入住时间！入住时间为必填项。</p>";
        // 高亮显示输入框
        checkinTimeInput.style.border = "2px solid #dc2626";
        checkinTimeInput.focus();
        setTimeout(() => {
            checkinTimeInput.style.border = "";
        }, 3000);
        return;
    }
    
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
        
        messageDiv.innerHTML = `<p style='color:#16a34a;'>✓ 房间 ${roomId} 登记入住成功！客人：${guestName}</p>`;
        
        // 清空表单
        guestNameInput.value = "";
        checkinTimeInput.value = "";
        checkoutTimeInput.value = "";
        
    } catch (error) {
        messageDiv.innerHTML = `<p style='color:#dc2626;'>✗ 登记入住失败：${error.message}</p>`;
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

// 加载账单
async function loadCheckoutBill() {
    const select = document.getElementById("co-room-select");
    const billTypeSelect = document.getElementById("co-bill-type");
    const container = document.getElementById("co-bill");
    const roomId = parseInt(select.value);
    
    if (!roomId) {
        container.innerHTML = "<p class='muted'>请先选择房间。</p>";
        return;
    }
    
    const billType = billTypeSelect ? billTypeSelect.value : 'accommodation';
    const endpoint = billType === 'ac' ? 'ac_bill' : 'accommodation_bill';
    
    try {
        const bill = await fetchJSON(`/api/bills/${roomId}/${endpoint}`);
        
        let html = `<h3>${bill.bill_type}</h3>`;
        html += `<table style="width:100%; border-collapse: collapse; font-size:13px;">`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>房间号</strong></td><td style="padding:6px; border:1px solid #eee;">${bill.room_id}</td></tr>`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>客人姓名</strong></td><td style="padding:6px; border:1px solid #eee;">${bill.guest_name}</td></tr>`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>入住时间</strong></td><td style="padding:6px; border:1px solid #eee;">${bill.checkin_time}</td></tr>`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>结束时间</strong></td><td style="padding:6px; border:1px solid #eee;">${bill.end_time}</td></tr>`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>住宿天数</strong></td><td style="padding:6px; border:1px solid #eee;">${bill.days} 天</td></tr>`;
        
        if (billType === 'accommodation') {
            html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>房间日租金</strong></td><td style="padding:6px; border:1px solid #eee;">¥${bill.daily_rate}</td></tr>`;
            html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>住宿费用</strong></td><td style="padding:6px; border:1px solid #eee;">¥${bill.accommodation_cost}</td></tr>`;
        }
        
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>空调费用</strong></td><td style="padding:6px; border:1px solid #eee;">¥${bill.ac_total_cost}</td></tr>`;
        html += `<tr><td style="padding:6px; border:1px solid #eee;"><strong>总计</strong></td><td style="padding:6px; border:1px solid #eee; font-weight:bold; font-size:16px;">¥${bill.total_cost}</td></tr>`;
        html += `</table>`;
        
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<p style='color:#dc2626;'>加载账单失败：${error.message}</p>`;
    }
}

// 导出Excel账单
async function exportBill() {
    const select = document.getElementById("co-room-select");
    const billTypeSelect = document.getElementById("co-bill-type");
    const roomId = parseInt(select.value);
    
    if (!roomId) {
        alert("请先选择房间");
        return;
    }
    
    const billType = billTypeSelect ? billTypeSelect.value : 'accommodation';
    
    try {
        // 直接下载Excel文件
        window.location.href = `/api/bills/${roomId}/export?bill_type=${billType}`;
    } catch (error) {
        alert("导出失败：" + error.message);
    }
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
                    <td>${record.request_time || '-'}</td>
                    <td>${record.start_time}</td>
                    <td>${record.end_time || '-'}</td>
                    <td>${record.service_duration || 0}</td>
                    <td>${record.fan_speed}</td>
                    <td>${record.cost.toFixed(2)}</td>
                    <td>${record.accumulated_cost.toFixed(2)}</td>
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

// 删除旧的loadCheckoutBill函数，已在上面重新定义

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
    const exportBtn = document.getElementById("co-export");
    const billTypeSelect = document.getElementById("co-bill-type");
    
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
    if (exportBtn) {
        exportBtn.onclick = () => exportBill();
    }
    // 账单类型改变时自动刷新账单
    if (billTypeSelect) {
        billTypeSelect.onchange = () => {
            const billDiv = document.getElementById("co-bill");
            if (billDiv && billDiv.innerHTML.includes("房间号")) {
                loadCheckoutBill();
            }
        };
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

// 实时刷新房间状态和队列信息
function startAutoRefresh() {
    // 每秒自动刷新房间列表和队列状态
    window.roomStatusInterval = setInterval(async () => {
        if (currentView === "admin") {
            try {
                await loadRooms();
                await loadQueues();
            } catch (error) {
                console.error("自动刷新失败:", error);
            }
        }
    }, 1000);
}

// 停止自动刷新
function stopAutoRefresh() {
    if (window.roomStatusInterval) {
        clearInterval(window.roomStatusInterval);
        window.roomStatusInterval = null;
    }
}

// 加载测试用例
async function applyInitialSettings() {
    // 应用初始温度设置到房间
    for (const [roomId, temp] of Object.entries(initialTemperatures)) {
        console.log(`设置${roomId}初始温度为${temp}°C`);
        try {
            // 从房间ID字符串中提取数字（如从R1提取1）
            const roomNum = parseInt(roomId.substring(1));
            
            // 调用初始化房间温度的API
            const response = await fetch('/api/rooms/initialize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    room_id: roomNum,
                    initial_temp: temp
                })
            });
            
            const result = await response.json();
            if (result.error) {
                console.error(`设置${roomId}初始温度失败:`, result.error);
            } else {
                console.log(`成功设置${roomId}初始温度为${temp}°C`);
            }
        } catch (error) {
            console.error(`设置${roomId}初始温度时发生错误:`, error);
        }
    }
    
    console.log(`默认风速设置为${defaultWindSpeed}`);
    // 默认风速将在房间开机时自动应用
}

// 确保testState对象已初始化
window.testState = window.testState || {
    mode: 'cooling', // 默认模式
    current_step: 0,
    total_steps: 0
};

async function loadTestCases(testType = null) {
    const loadBtn = document.getElementById('load-test-btn');
    const coolingBtn = document.getElementById('cooling-test-btn');
    const heatingBtn = document.getElementById('heating-test-btn');
    const startBtn = document.getElementById('start-test-btn');
    
    try {
        // 禁用按钮防止重复点击
        if (loadBtn) loadBtn.disabled = true;
        if (coolingBtn) coolingBtn.disabled = true;
        if (heatingBtn) heatingBtn.disabled = true;
        
        if (loadBtn && !testType) loadBtn.textContent = '加载中...';
        if (coolingBtn && testType === 'cooling') coolingBtn.textContent = '加载中...';
        if (heatingBtn && testType === 'heating') heatingBtn.textContent = '加载中...';
        
        // 构建URL，添加测试类型参数
        const url = testType ? `/api/test/load?type=${testType}` : '/api/test/load';
        const response = await fetchJSON(url);
        
        if (response.success) {
            alert(response.message);
            totalTestMinutes = response.total_minutes;
            currentTestMinute = 0;
            
            // 保存测试模式
            testState.mode = testType || 'cooling';
            console.log('测试模式设置:', testState.mode);
            
            // 保存初始温度和默认风速设置
            if (response.initial_temperatures) {
                initialTemperatures = response.initial_temperatures;
                console.log('初始温度设置:', initialTemperatures);
            }
            if (response.default_wind_speed) {
                defaultWindSpeed = response.default_wind_speed;
                console.log('默认风速设置:', defaultWindSpeed);
            }
            
            // 启用开始按钮和一键执行按钮
            if (startBtn) startBtn.disabled = false;
            const autoBtn = document.getElementById('auto-test-btn');
            if (autoBtn) autoBtn.disabled = false;
            
            // 重置当前时刻为0
            currentTestMinute = 0;
            
            // 更新测试状态显示
            updateTestStatus();
            
            // 根据初始温度设置房间状态
            applyInitialSettings();
        } else {
            alert(response.message);
        }
    } catch (error) {
        alert('加载测试用例失败: ' + error.message);
    } finally {
        // 恢复按钮状态
        if (loadBtn) {
            loadBtn.disabled = false;
            loadBtn.textContent = '加载测试用例';
        }
        if (coolingBtn) {
            coolingBtn.disabled = false;
            coolingBtn.textContent = '制冷测试';
        }
        if (heatingBtn) {
            heatingBtn.disabled = false;
            heatingBtn.textContent = '制热测试';
        }
    }
}

// 执行房间操作
async function executeRoomOperation(operation) {
    const roomId = operation.room_id;
    const numericRoomId = roomId.substring(1); // 从R1提取1
    
    try {
        switch (operation.type) {
            case 'power_on':
                // 不传递current_temp参数，让后端使用房间的实际温度
                // 初始温度只在测试开始时通过applyInitialSettings函数设置
                // 传递正确的模式参数，基于测试状态中的mode值
                const mode = testState.mode === 'heating' ? 'HEAT' : 'COOL';
                await fetchJSON(`/api/rooms/${numericRoomId}/power_on`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: mode })
                });
                console.log(`房间${roomId}开机成功，使用当前实际温度，模式: ${mode}`);
                break;
            case 'power_off':
                await fetchJSON(`/api/rooms/${numericRoomId}/power_off`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                console.log(`房间${roomId}关机成功`);
                break;
            case 'adjust_temperature':
                await fetchJSON(`/api/rooms/${numericRoomId}/adjust_temperature`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_temp: operation.target_temp })
                });
                console.log(`房间${roomId}调温至${operation.target_temp}℃成功`);
                break;
            case 'adjust_wind_speed':
                // 使用字符串拼接代替模板字符串，避免可能的解析问题
                await fetchJSON('/api/rooms/' + numericRoomId + '/adjust_speed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ speed: operation.speed })
                });
                console.log('房间' + roomId + '调风速至' + operation.speed + '成功');
                break;
        }
    } catch (error) {
        console.error(`执行房间${roomId}的${operation.type}操作失败:`, error);
    }
}

// 10秒动态模拟60秒
async function simulateMinute() {
    // 10秒动态模拟1分钟（分10次，每次6秒）
    const totalSeconds = 60; // 总共要模拟的秒数
    const steps = 10; // 分10步完成
    const secondsPerStep = totalSeconds / steps; // 每步6秒
    const delayBetweenSteps = 1000; // 每步间隔1秒（总共10秒）
    
    for (let i = 0; i < steps && !testPaused; i++) {
        // 模拟当前步骤的时间
        await fetchJSON("/api/tick", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({seconds: secondsPerStep})
        });
        
        // 更新UI显示最新状态
        await loadRooms();
        await loadQueues(); // 更新队列信息
        
        // 如果暂停了，跳出循环
        if (testPaused) break;
        
        // 如果不是最后一步，等待1秒
        if (i < steps - 1) {
            await new Promise(resolve => {
                const timeoutId = setTimeout(resolve, delayBetweenSteps);
                // 支持暂停的检查
                if (testPaused) clearTimeout(timeoutId);
            });
        }
    }
}

// 执行当前时刻的测试用例
async function executeCurrentStep() {
    const startBtn = document.getElementById('start-test-btn');
    const nextBtn = document.getElementById('next-step-btn');
    const loadBtn = document.getElementById('load-test-btn');
    const tickBtn = document.getElementById('tick-btn');
    const statusDiv = document.getElementById('test-status');
    
    try {
        // 禁用相关按钮
        if (startBtn) startBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
        if (loadBtn) loadBtn.disabled = true;
        if (tickBtn) tickBtn.disabled = true;
        
        // 检查是否有测试用例
        if (totalTestMinutes === 0) {
            alert('请先加载测试用例');
            return;
        }
        
        // 检查是否已经执行完所有时刻
        if (currentTestMinute >= totalTestMinutes) {
            alert('所有测试用例已执行完毕');
            updateTestStatus();
            return;
        }
        
        // 开始执行当前时刻的操作
        const response = await fetchJSON('/api/test/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.success) {
            alert(response.message);
            return;
        }
        
        // 更新初始设置（如果服务器返回新的设置）
        if (response.initial_temperatures) {
            initialTemperatures = response.initial_temperatures;
        }
        if (response.default_wind_speed) {
            defaultWindSpeed = response.default_wind_speed;
        }
        
        console.log(`执行时刻${currentTestMinute}的操作`);
        
        // 更新状态显示
        if (statusDiv) {
            statusDiv.innerHTML = `<span style="color:#2196F3;">正在执行时刻 ${currentTestMinute} 的操作...</span>`;
        }
        
        // 执行当前时刻的所有操作
        for (const operation of response.operations) {
            await executeRoomOperation(operation);
            // 短暂延迟，确保操作顺序执行
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        // 更新UI
        await loadRooms();
        await loadQueues();
        
        // 动态模拟60秒（10秒实际时间）
        if (statusDiv) {
            statusDiv.innerHTML = `<span style="color:#2196F3;">正在模拟时间前进1分钟...</span>`;
        }
        await simulateMinute();
        
        // 前进到下一个时刻
        const nextResponse = await fetchJSON('/api/test/next', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (nextResponse.success) {
            currentTestMinute = nextResponse.current_minute;
            
            // 更新状态显示
            updateTestStatus();
            
            if (!nextResponse.has_next) {
                alert('所有测试用例执行完毕');
                if (startBtn) startBtn.disabled = true;
                if (nextBtn) nextBtn.style.display = 'none';
            } else {
                // 启用下一步按钮
                if (nextBtn) {
                    nextBtn.style.display = 'inline-block';
                    nextBtn.disabled = false;
                }
            }
        } else {
            alert(nextResponse.message);
        }
    } catch (error) {
        alert('测试执行失败: ' + error.message);
        console.error('测试执行错误:', error);
    } finally {
        // 恢复按钮状态
        if (startBtn) startBtn.disabled = false;
        if (loadBtn) loadBtn.disabled = false;
        if (tickBtn) tickBtn.disabled = false;
    }
}

// 更新测试状态显示
function updateTestStatus() {
    const statusDiv = document.getElementById('test-status');
    if (statusDiv) {
        if (totalTestMinutes === 0) {
            statusDiv.innerHTML = '<span class="muted">请先加载测试用例</span>';
        } else if (currentTestMinute >= totalTestMinutes) {
            statusDiv.innerHTML = '<span style="color:#4CAF50;">✓ 所有测试用例已执行完毕</span>';
        } else {
            statusDiv.innerHTML = `<span>当前时刻: ${currentTestMinute} / ${totalTestMinutes - 1}</span>`;
        }
    }
}

// 下一步操作
async function nextStep() {
    await executeCurrentStep();
}

// 一键执行所有测试用例（自动执行）
async function startAutoTest() {
    const autoBtn = document.getElementById('auto-test-btn');
    const startBtn = document.getElementById('start-test-btn');
    const nextBtn = document.getElementById('next-step-btn');
    const loadBtn = document.getElementById('load-test-btn');
    const tickBtn = document.getElementById('tick-btn');
    const statusDiv = document.getElementById('test-status');
    
    try {
        // 禁用相关按钮
        if (autoBtn) autoBtn.disabled = true;
        if (startBtn) startBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
        if (loadBtn) loadBtn.disabled = true;
        if (tickBtn) tickBtn.disabled = true;
        
        testRunning = true;
        testPaused = false;
        
        // 检查是否有测试用例
        if (totalTestMinutes === 0) {
            alert('请先加载测试用例');
            return;
        }
        
        // 重置当前时刻为0
        currentTestMinute = 0;
        
        console.log('开始一键执行测试，初始设置已加载:');
        console.log('- 初始温度:', initialTemperatures);
        console.log('- 默认风速:', defaultWindSpeed);
        
        while (testRunning && currentTestMinute < totalTestMinutes && !testPaused) {
            // 开始执行当前时刻的操作
            const response = await fetchJSON('/api/test/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.success) {
                alert(response.message);
                break;
            }
            
            // 更新初始设置（如果服务器返回新的设置）
            if (response.initial_temperatures) {
                initialTemperatures = response.initial_temperatures;
            }
            if (response.default_wind_speed) {
                defaultWindSpeed = response.default_wind_speed;
            }
            
            console.log(`执行时刻${currentTestMinute}的操作`);
            
            // 更新状态显示
            if (statusDiv) {
                statusDiv.innerHTML = `<span style="color:#2196F3;">正在执行时刻 ${currentTestMinute} / ${totalTestMinutes - 1}...</span>`;
            }
            
            // 执行当前时刻的所有操作
            for (const operation of response.operations) {
                await executeRoomOperation(operation);
                // 短暂延迟，确保操作顺序执行
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            // 更新UI
            await loadRooms();
            await loadQueues();
            
            // 动态模拟60秒（10秒实际时间）
            if (statusDiv) {
                statusDiv.innerHTML = `<span style="color:#2196F3;">正在模拟时间前进1分钟... (${currentTestMinute + 1}/${totalTestMinutes})</span>`;
            }
            await simulateMinute();
            
            if (testPaused) break;
            
            // 前进到下一个时刻
            const nextResponse = await fetchJSON('/api/test/next', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (nextResponse.success) {
                currentTestMinute = nextResponse.current_minute;
                
                if (!nextResponse.has_next) {
                    if (statusDiv) {
                        statusDiv.innerHTML = '<span style="color:#4CAF50;">✓ 所有测试用例执行完毕</span>';
                    }
                    alert('所有测试用例执行完毕');
                    testRunning = false;
                    break;
                }
            } else {
                alert(nextResponse.message);
                break;
            }
        }
    } catch (error) {
        alert('测试执行失败: ' + error.message);
        console.error('测试执行错误:', error);
    } finally {
        // 恢复按钮状态
        if (!testPaused) {
            testRunning = false;
            if (autoBtn) autoBtn.disabled = false;
            if (startBtn) startBtn.disabled = false;
            if (loadBtn) loadBtn.disabled = false;
            if (tickBtn) tickBtn.disabled = false;
        }
        // 更新测试状态显示
        updateTestStatus();
    }
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
    
    // 重置累计费用按钮
    const resetCostBtn = document.getElementById("admin-reset-cost");
    if (resetCostBtn) {
        resetCostBtn.onclick = () => adminResetRoomCost();
    }
    
    // 模拟前进按钮
    const tickBtn = document.getElementById("tick-btn");
    if (tickBtn) {
        tickBtn.onclick = async () => {
            // 禁用按钮防止重复点击
            tickBtn.disabled = true;
            tickBtn.textContent = "模拟中...";
            
            // 10秒动态模拟1分钟（分10次，每次6秒）
            const totalSeconds = 60; // 总共要模拟的秒数
            const steps = 10; // 分10步完成
            const secondsPerStep = totalSeconds / steps; // 每步6秒
            const delayBetweenSteps = 1000; // 每步间隔1秒（总共10秒）
            
            for (let i = 0; i < steps; i++) {
                // 模拟当前步骤的时间
                await fetchJSON("/api/tick", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({seconds: secondsPerStep})
                });
                
                // 更新UI显示最新状态
                await loadRooms();
                await loadQueues(); // 更新队列信息
                
                // 更新按钮进度显示
                const progress = Math.round((i + 1) / steps * 100);
                tickBtn.textContent = `模拟中... ${progress}%`;
                
                // 如果不是最后一步，等待1秒
                if (i < steps - 1) {
                    await new Promise(resolve => setTimeout(resolve, delayBetweenSteps));
                }
            }
            
            // 恢复按钮状态
            tickBtn.disabled = false;
            tickBtn.textContent = "模拟前进 1 分钟（10秒动态模拟）";
        };
    }

    // 前台、经理界面初始化
    initFrontdeskView();
    initManagerView();
    
    // 测试用例相关按钮事件
    const loadTestBtn = document.getElementById('load-test-btn');
    const coolingTestBtn = document.getElementById('cooling-test-btn');
    const heatingTestBtn = document.getElementById('heating-test-btn');
    const autoTestBtn = document.getElementById('auto-test-btn');
    const startTestBtn = document.getElementById('start-test-btn');
    const nextStepBtn = document.getElementById('next-step-btn');
    
    if (loadTestBtn) {
        loadTestBtn.onclick = () => loadTestCases();
    }
    
    if (coolingTestBtn) {
        coolingTestBtn.onclick = () => loadTestCases('cooling');
    }
    
    if (heatingTestBtn) {
        heatingTestBtn.onclick = () => loadTestCases('heating');
    }
    
    if (autoTestBtn) {
        autoTestBtn.disabled = true; // 初始禁用，加载测试用例后启用
        autoTestBtn.onclick = startAutoTest;
    }
    
    if (startTestBtn) {
        startTestBtn.disabled = true; // 初始禁用，加载测试用例后启用
        startTestBtn.onclick = executeCurrentStep;
    }
    
    if (nextStepBtn) {
        nextStepBtn.onclick = nextStep;
    }
    
    // 初始化测试状态显示
    updateTestStatus();
    
    // 启动自动刷新
    startAutoRefresh();
    
    // 页面卸载时清理定时器
    window.addEventListener('beforeunload', stopAutoRefresh);
    
    // 清理测试相关的定时器
    window.addEventListener('beforeunload', () => {
        testRunning = false;
        testPaused = false;
        if (testSimulationInterval) {
            clearInterval(testSimulationInterval);
        }
    });
}

window.addEventListener("load", init);

