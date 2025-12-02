## 酒店自助计费中央空调系统说明文档

### 一、项目简介

本项目实现了一个**快捷廉价酒店自助计费式中央温控系统**的核心逻辑，用于课程/实验作业或原型演示。  
系统支持：

- **房客端功能**：
  - 开关机、制冷/制热模式切换；
  - 设置目标温度（按要求限制在给定范围内）；
  - 调节风速（高 / 中 / 低），并按风速计费；
  - 温度传感与面板显示（通过模拟逻辑实时更新房间温度）。
- **前台/管理员功能**：
  - 查询每个房间当前状态（温度、模式、风速、送风/等待/关机状态等）；
  - 生成退房时的**空调使用账单及汇总信息**；
  - 中央空调管理员可实时监控所有房间运行状态；
  - 酒店经理可查看整体能耗与费用的**统计报表**。

本实现采用 **Python** 编写，使用**面向对象 + 调度器**的方式模拟中央空调系统的行为，重点体现：

- **温控范围与物理模型**；
- **计费与能耗模型**；
- **优先级调度 + 时间片调度**；
- **温度按钮防抖逻辑**。

> 说明：本项目主要是后端逻辑模拟，没有 GUI，只需在命令行运行并查看输出即可。

---

### 二、需求对应说明

#### 1. 温控范围与模式

- 制冷模式（`Mode.COOL`）：温度范围 **18–25°C**；
- 制热模式（`Mode.HEAT`）：温度范围 **25–30°C**；
- 系统默认温度：`25°C`（常量 `DEFAULT_TEMP`）。

在代码中，目标温度通过 `CentralACSystem._clamp_target_temp()` 进行范围限制：

- 制冷：\[18, 25\]；
- 制热：\[25, 30\]。

#### 2. 计费与耗电标准

- **计费标准**：`1 元 / 度`（`CentralACSystem.price_per_energy = 1.0`）。
- **耗电标准**（代码中以“度 / 分钟”为单位）：
  - 高风：`1 度 / 分钟`；
  - 中风：`0.5 度 / 分钟`（即 1 度 / 2 分钟）；
  - 低风：`1/3 度 / 分钟`（即 1 度 / 3 分钟）。

能耗与费用模型在 `CentralACSystem._update_room_serving()` 中实现：

- 每秒能耗 = 每分钟能耗 / 60；
- 房间对象 `Room` 中记录：
  - `energy_used`：总耗电“度”；
  - `cost`：总费用（`energy_used * 价格`）。

#### 3. 温度变化模式

在 `CentralACSystem._update_room_serving()` 和 `_update_room_temp_off()` 中实现：

- **送风状态**：
  - 中风：`0.5°C / 分钟`；
  - 高风：`0.5 * 1.2 = 0.6°C / 分钟`；
  - 低风：`0.5 * 0.8 = 0.4°C / 分钟`；
  - 制冷：在当前温度 > 目标温度时降温，不能降过头；
  - 制热：在当前温度 < 目标温度时升温，不能升过头。
- **关机/未送风状态**：
  - 按 `0.5°C / 分钟` 的速度向房间 `initial_temp` 回归（在 `_update_room_temp_off()` 中实现）。

#### 4. 自动停止与重启

在 `CentralACSystem._auto_stop_and_restart()` 中实现：

- **停止送风**：
  - 制冷：当 `current_temp <= target_temp` 时，自动 `power_off(room_id)`；
  - 制热：当 `current_temp >= target_temp` 时，自动 `power_off(room_id)`。
- **自动重启**：
  - 制冷模式：当 `current_temp >= target_temp + 1°C` 时自动重新发起送风请求；
  - 制热模式：当 `current_temp <= target_temp - 1°C` 时自动重新发起送风请求；
  - 重启时沿用当前房间的 `mode` 与 `fan_speed`。

#### 5. 调度：优先级 + 时间片

在 `Scheduler` 类中实现：

- **服务能力受限**：调度器初始化时传入 `capacity = y`，最多同时服务 y 间房；
- **优先级调度（风速优先）**：
  - `FanSpeed.HIGH > MEDIUM > LOW`；
  - 新送风请求若风速**高于**正在服务的某房间：
    - 通过 `_find_lowest_priority_active()` 找到当前优先级最低的活动请求；
    - 若新请求风速更高，则新请求**立即抢占**其服务：
      - 被抢占房间转入等待队列；
      - 新房间进入 `active_requests`。
- **时间片调度（相同风速轮转）**：
  - 每个请求维护：
    - `total_served_seconds`（累计送风时间）；
    - `waiting_seconds`（自上次开始等待起已等待多久）。
  - 在 `Scheduler.tick()` 中：
    - 每秒更新所有请求的服务/等待时间；
    - 对 `waiting_seconds >= time_slice` 的等待请求：
      - 找出同风速下在服务中、`total_served_seconds` **最长**的房间作为被轮转对象；
      - 被轮转房间进入等待队列；
      - 等待满时间片的房间进入服务队列；
      - 以此实现 **“等待一段时间后（s 秒）获得送风服务，获得服务时间最长的房间被暂停”** 的轮转规则。

#### 6. 风速/温度调整与请求生成规则

- **风速调整**：在 `CentralACSystem.adjust_fan_speed()` 中实现：
  - 调节风速视为**新的送风请求**；
  - 将旧请求（若有）移除，提交新的 `ACRequest` 给调度器。
- **温度调整**：在 `CentralACSystem.adjust_temperature()` 中实现：
  - 只改变目标温度，不产生新的送风请求；
  - 仅更新房间对象中的 `target_temp`。

#### 7. 温度按钮防抖逻辑

在 `CommandDebouncer` 类中实现：

- 输入：`List[Tuple[timestamp, value]]`，时间单位为秒，可为 `float`；
- 规则：
  - 若两次指令的时间间隔 `< 1 秒`，只保留该组中**最后一次指令参数**；
  - 若间隔 `>= 1 秒`，则两次请求都保留；
- 输出：过滤后的指令列表，可用于实际发送给服务端。

---

### 三、代码结构与主要类

#### 1. 文件结构

- 领域层（按你给的类名拆分）：
  - `ac_core/models.py`：`Mode`、`FanSpeed`、`PowerState`、`Room` 以及 `RoomRepository`（房间仓储）。
  - `ac_core/queues.py`：`ServedQueue`（服务队列）、`WaitingQueue`（等待队列）、`ServiceState`。
  - `ac_core/timers.py`：`ServiceTimer`（服务计时器）、`WaitTimer`（等待计时器）。
  - `ac_core/server.py`：`Server`（服务对象，负责温控参数设置与温度变化）。
  - `ac_core/records.py`：`DetailRecord`（详单对象，负责操作记录与费用计算，并持久化 SQLite）。
  - `ac_core/scheduler.py`：`Scheduler`（调度对象）与 `HotelACSystem`（系统封装，对外入口）。
  - `ac_core/__init__.py`：对外统一导出上述核心类。
- 原有纯模拟版（保留）：
  - `central_ac.py`：早期的单文件模拟实现，仍可单独运行 `python central_ac.py` 进行命令行演示。
- 后端与前端：
  - `backend_app.py`：Flask Web 后端，提供 REST 接口和静态页面服务。
  - `frontend/index.html`：简单 Web 控制台页面。
  - `frontend/app.js`：前端逻辑，调用后端接口完成开机、关机、调风速、查看账单与报表等操作。

#### 2. 重要接口说明

- **系统初始化**

  ```python
  from central_ac import CentralACSystem, Mode, FanSpeed

  # x 间房，y 间同时服务，时间片 s 秒
  system = CentralACSystem(room_count=x, service_capacity=y, time_slice_seconds=s)
  ```

- **房间开机/设定**

  ```python
  system.power_on(
      room_id=1,
      mode=Mode.COOL,          # 或 Mode.HEAT
      target_temp=22.0,
      fan_speed=FanSpeed.HIGH  # HIGH / MEDIUM / LOW
  )
  ```

- **关机**

  ```python
  system.power_off(room_id=1)
  ```

- **只调温（不产生新请求）**

  ```python
  system.adjust_temperature(room_id=1, new_target_temp=23.0)
  ```

- **调速（产生新送风请求）**

  ```python
  system.adjust_fan_speed(room_id=1, new_fan_speed=FanSpeed.MEDIUM)
  ```

- **时间推进（模拟运行）**

  ```python
  # 模拟 1 小时（3600 秒）
  system.tick(3600)
  ```

- **查询状态（管理员监控用）**

  ```python
  # 单个房间
  status = system.get_room_status(1)

  # 所有房间
  all_status = system.get_all_rooms_status()
  ```

- **账单与报表**

  ```python
  # 某房间退房账单
  bill = system.get_bill_for_room(1)

  # 总体统计报表
  report = system.get_summary_report()
  ```

- **按钮防抖示例**

  ```python
  from central_ac import CommandDebouncer

  # (时间戳, 目标温度)
  raw_cmds = [
      (0.0, 24.0),
      (0.3, 23.0),  # 与上次间隔 < 1 秒，将被合并，只保留 23.0
      (1.5, 22.0),  # 与上次间隔 >= 1 秒，单独发送
  ]
  real_cmds = CommandDebouncer.debounce(raw_cmds)
  ```

---

### 四、运行示例

#### 1. 运行 Web 版前后端

1. 安装依赖（只用到 Flask，可选）：

   ```bash
   pip install flask
   ```

2. 在项目根目录运行后端：

   ```bash
   python backend_app.py
   ```

3. 浏览器访问 `http://127.0.0.1:5000/`，即可看到“酒店自助计费中央空调系统”界面：

   - 左侧为房间列表（温度、模式、风速、状态、费用等）；
   - 右侧为选中房间的“开机 / 关机 / 调风速 / 查看详单”控制区以及总体统计报表；
   - 点击“模拟前进 60 秒”按钮，可推进系统时间，观察温度与费用变化。

4. 所有开机、调风速等操作都会写入 SQLite 数据库 `hotel_ac.db` 的 `detail_records` 表，可用于退房结算和统计分析。

#### 2. 运行命令行模拟版（可选）

保留原有 `central_ac.py` 的命令行 demo：

```bash
python central_ac.py
```


---

### 五、扩展与优化方向（可选）

若作为课程设计或进一步项目，可在本基础上扩展：

- **增加持久化**：将账单、详单和报表写入数据库或文件；
- **增加前端界面**：使用 Web / 桌面 UI 显示房客面板、管理员监控界面；
- **完善时间范围报表**：按任意时间区间统计不同房间或楼层的能耗；
- **更精细的物理模型**：考虑室外温度、热负荷等因素；
- **异常处理与日志**：记录设备故障、非法操作等。

本项目当前版本侧重于**正确实现题目给出的业务规则与调度算法**，结构清晰，便于进一步扩展和二次开发。


