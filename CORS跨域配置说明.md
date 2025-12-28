# CORS跨域配置说明

## 问题描述

在其他电脑运行客户端时，出现"切换电源状态失败"的错误。

## 问题原因

这是**CORS（跨域资源共享）**问题：

当客户端和服务端在不同电脑（或不同端口）时，浏览器的同源策略会阻止跨域请求。

### 同源策略

浏览器只允许以下情况的请求：
- 相同协议（http/https）
- 相同域名
- 相同端口

### 跨域场景

```
客户端电脑：http://192.168.1.50:5000/client/room_remote.html
服务端电脑：http://192.168.1.100:5000/api/rooms/1/power_on

❌ 不同域名 → 跨域请求被阻止
```

## 解决方案

添加 **flask-cors** 支持，允许跨域请求。

### 1. 安装依赖

```bash
pip install flask-cors
```

或使用requirements.txt：
```bash
pip install -r requirements.txt
```

### 2. 配置CORS

在 `backend_app.py` 中添加：

```python
from flask_cors import CORS

# 配置CORS，允许跨域请求
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # 允许所有来源
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

## 配置说明

### CORS配置参数

| 参数 | 说明 | 值 |
|------|------|-----|
| `origins` | 允许的来源 | `"*"` 表示允许所有来源 |
| `methods` | 允许的HTTP方法 | GET, POST, PUT, DELETE, OPTIONS |
| `allow_headers` | 允许的请求头 | Content-Type, Authorization |

### 安全考虑

**开发环境**：
- `origins: "*"` - 允许所有来源（方便开发测试）

**生产环境**（可选）：
```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://192.168.1.50", "http://192.168.1.51"],  # 只允许特定IP
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

## 工作原理

### 请求流程

1. **客户端发送请求**
   ```
   POST http://192.168.1.100:5000/api/rooms/1/power_on
   Origin: http://192.168.1.50:5000
   ```

2. **浏览器发送预检请求（OPTIONS）**
   ```
   OPTIONS http://192.168.1.100:5000/api/rooms/1/power_on
   Origin: http://192.168.1.50:5000
   Access-Control-Request-Method: POST
   ```

3. **服务端响应（带CORS头）**
   ```
   Access-Control-Allow-Origin: *
   Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
   Access-Control-Allow-Headers: Content-Type, Authorization
   ```

4. **浏览器允许实际请求**
   ```
   POST http://192.168.1.100:5000/api/rooms/1/power_on
   ```

## 测试验证

### 测试步骤

1. **安装依赖**
   ```bash
   pip install flask-cors
   ```

2. **重启服务端**
   ```bash
   python backend_app.py
   ```

3. **在客户端电脑测试**
   - 打开浏览器开发者工具（F12）
   - 查看Network标签页
   - 尝试切换电源状态
   - 检查请求是否成功

### 验证CORS是否生效

在浏览器控制台查看：

**成功**：
```
✓ 请求成功，状态码200
✓ 响应头包含 Access-Control-Allow-Origin: *
```

**失败**（未配置CORS）：
```
✗ CORS policy: No 'Access-Control-Allow-Origin' header
✗ 请求被阻止
```

## 常见错误

### 错误1：ModuleNotFoundError: No module named 'flask_cors'

**解决**：
```bash
pip install flask-cors
```

### 错误2：仍然显示跨域错误

**检查**：
1. 确认已安装flask-cors
2. 确认已重启服务端
3. 检查浏览器控制台的详细错误信息

### 错误3：OPTIONS请求失败

**原因**：某些服务器配置问题

**解决**：flask-cors会自动处理OPTIONS请求

## 修改的文件

1. **backend_app.py**
   - 导入 `flask_cors`
   - 配置CORS

2. **requirements.txt**
   - 添加 `flask-cors>=3.0.0`

3. **hotel/hotel/backend_app.py** - 同步更新

## 使用效果

### 配置前
```
客户端 → 服务端
❌ 跨域请求被阻止
❌ 切换电源状态失败
```

### 配置后
```
客户端 → 服务端
✅ CORS允许跨域请求
✅ 切换电源状态成功
```

## 更新日期
2025年

## 相关文档
- [跨机器运行配置说明.md](./跨机器运行配置说明.md) - 网络配置
- [开机失败问题修复说明.md](./开机失败问题修复说明.md) - 开机问题修复

