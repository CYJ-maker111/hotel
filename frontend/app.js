let selectedRoomId = null;

async function fetchJSON(url, options) {
    const res = await fetch(url, options);
    return await res.json();
}

function stateBadge(state) {
    if (state === "serving") return '<span class="badge serving">送风</span>';
    if (state === "waiting") return '<span class="badge waiting">等待</span>';
    return '<span class="badge off">关机</span>';
}

async function loadRooms() {
    const rooms = await fetchJSON("/api/rooms");
    const tbody = document.querySelector("#rooms-table tbody");
    tbody.innerHTML = "";
    rooms.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${r.room_id}</td>
            <td>${stateBadge(r.state)}</td>
            <td>${r.current_temp} ℃</td>
            <td>${r.mode}</td>
            <td>${r.fan_speed}</td>
            <td>${r.cost}</td>
            <td><button data-room="${r.room_id}" class="primary">选择</button></td>
        `;
        tbody.appendChild(tr);
    });
    tbody.querySelectorAll("button").forEach(btn => {
        btn.onclick = () => {
            selectedRoomId = parseInt(btn.dataset.room, 10);
            renderRoomControl();
        };
    });
}

async function loadSummary() {
    const s = await fetchJSON("/api/report/summary");
    const div = document.getElementById("summary");
    div.innerHTML = `
        总耗电：<b>${s.total_energy.toFixed(4)}</b> 度<br>
        总费用：<b>${s.total_cost.toFixed(2)}</b> 元
    `;
}

async function renderRoomControl() {
    const container = document.getElementById("room-control");
    if (!selectedRoomId) {
        container.innerHTML = "<p>请先在左侧点击选择一个房间。</p>";
        return;
    }
    const rooms = await fetchJSON("/api/rooms");
    const room = rooms.find(r => r.room_id === selectedRoomId);
    if (!room) return;

    container.innerHTML = `
        <p>当前房间：<b>${room.room_id}</b></p>
        <p>状态：${stateBadge(room.state)}</p>
        <p>当前温度：${room.current_temp} ℃，模式：${room.mode}，风速：${room.fan_speed}</p>
        <p>当前费用：<b>${room.cost}</b> 元</p>
        <div class="row controls">
            <div>
                <label>当前室温 (℃)</label>
                <input type="number" id="current-temp" value="${room.current_temp}" step="0.1">
            </div>
            <div>
                <label>风速</label>
                <select id="fan-speed">
                    <option value="LOW">低风</option>
                    <option value="MEDIUM">中风</option>
                    <option value="HIGH">高风</option>
                </select>
            </div>
        </div>
        <div style="margin-top:8px;">
            <button id="power-on-btn" class="primary">开机/重新开机</button>
            <button id="power-off-btn" class="danger">关机</button>
            <button id="change-speed-btn">调节风速</button>
            <button id="show-bill-btn">查看详单</button>
        </div>
        <div id="bill" style="margin-top:8px;font-size:12px;"></div>
    `;
    document.getElementById("fan-speed").value = room.fan_speed;

    document.getElementById("power-on-btn").onclick = async () => {
        const temp = parseFloat(document.getElementById("current-temp").value || "25");
        await fetchJSON(`/api/rooms/${room.room_id}/power_on`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({current_temp: temp})
        });
        await loadRooms();
        await loadSummary();
        await renderRoomControl();
    };
    document.getElementById("power-off-btn").onclick = async () => {
        await fetchJSON(`/api/rooms/${room.room_id}/power_off`, {method: "POST"});
        await loadRooms();
        await loadSummary();
        await renderRoomControl();
    };
    document.getElementById("change-speed-btn").onclick = async () => {
        const speed = document.getElementById("fan-speed").value;
        await fetchJSON(`/api/rooms/${room.room_id}/adjust_speed`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({speed})
        });
        await loadRooms();
        await loadSummary();
        await renderRoomControl();
    };
    document.getElementById("show-bill-btn").onclick = async () => {
        const bill = await fetchJSON(`/api/rooms/${room.room_id}/bill`);
        const div = document.getElementById("bill");
        let html = `<b>总耗电：</b>${bill.total_energy} 度，<b>总费用：</b>${bill.total_cost} 元<br>`;
        html += "<table><tr><th>ID</th><th>开始时间</th><th>结束时间</th><th>模式</th><th>目标温度</th><th>风速</th><th>费率</th><th>耗电</th><th>费用</th><th>类型</th></tr>";
        bill.details.forEach(d => {
            html += `<tr>
                <td>${d.id}</td>
                <td>${d.start_time}</td>
                <td>${d.end_time || ""}</td>
                <td>${d.mode}</td>
                <td>${d.target_temp}</td>
                <td>${d.fan_speed}</td>
                <td>${d.fee_rate}</td>
                <td>${d.energy_used}</td>
                <td>${d.cost}</td>
                <td>${d.operation_type}</td>
            </tr>`;
        });
        html += "</table>";
        div.innerHTML = html;
    };
}

async function init() {
    await loadRooms();
    await loadSummary();
    document.getElementById("tick-btn").onclick = async () => {
        await fetchJSON("/api/tick", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({seconds: 60})
        });
        await loadRooms();
        await loadSummary();
        await renderRoomControl();
    };
}

window.addEventListener("load", init);


