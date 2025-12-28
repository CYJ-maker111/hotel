# API地址自动配置说明

## 问题描述

访问 `http://10.129.30.39:5000/client/room_remote.html` 时无法进行开机等操作，但访问 `http://127.0.0.1:5000/client/room_remote.html` 可以正常操作。

## 问题原因

客户端代码中的 `API_BASE_URL` 默认值是硬编码的 `http://127.0.0.1:5000/api`。

当访问 `http://10.129.30.39:5000/client/room_remote.html` 时：
- 页面从 `10.129.30.39:5000` 加载
- 但API请求发送到 `127.0.0.1:5000/api`（错误地址）
- 导致请求失败

## 解决方案

**自动从当前页面URL提取主机和端口，构建API地址**

### 修改前

```javascript
const API_BASE_URL = urlParams.get('api') || 'http://127.0.0.1:5000/api';
// 总是使用默认值 127.0.0.1
```

### 修改后

```javascript
const urlParams = new URLSearchParams(window.location.search);
let API_BASE_URL = urlParams.get('api');

// 如果没有通过URL参数指定，则自动从当前页面URL构建
if (!API_BASE_URL) {
    const protocol = window.location.protocol; // http: 或 https:
    const hostname = window.location.hostname; // 10.129.30.39 或 127.0.0.1
    const port = window.location.port || (protocol === 'https:' ? '443' : '80');
    
    // 构建API地址
    if (port && port !== '80' && port !== '443') {
        API_BASE_URL = `${protocol}//${hostname}:${port}/api`;
    } else {
        API_BASE_URL = `${protocol}//${hostname}/api`;
    }
}
```

## 工作原理

### 自动提取逻辑

1. **检查URL参数**：优先使用 `?api=...` 参数
2. **自动构建**：从 `window.location` 提取：
   - `protocol`：协议（http: 或 https:）
   - `hostname`：主机名（IP地址或域名）
   - `port`：端口号

### 示例

| 访问地址 | 自动构建的API地址 |
|---------|-----------------|
| `http://127.0.0.1:5000/client/room_remote.html` | `http://127.0.0.1:5000/api` |
| `http://10.129.30.39:5000/client/room_remote.html` | `http://10.129.30.39:5000/api` |
| `http://192.168.1.100:5000/client/room_remote.html` | `http://192.168.1.100:5000/api` |
| `http://localhost:5000/client/room_remote.html` | `http://localhost:5000/api` |

## 使用方式

### 方式1：自动配置（推荐）

直接访问，无需任何参数：
```
http://10.129.30.39:5000/client/room_remote.html
```

API地址会自动设置为：`http://10.129.30.39:5000/api`

### 方式2：手动指定（高级）

如果需要指定不同的API地址：
```
http://10.129.30.39:5000/client/room_remote.html?api=http://192.168.1.100:5000/api
```

## 验证方法

### 1. 打开浏览器控制台

按 `F12` 打开开发者工具，查看Console标签页。

### 2. 查看API地址

页面加载后，会输出：
```
API_BASE_URL: http://10.129.30.39:5000/api
```

### 3. 测试操作

尝试开机、调温等操作，查看Network标签页：
- 请求URL应该是：`http://10.129.30.39:5000/api/rooms/1/power_on`
- 不应该出现：`http://127.0.0.1:5000/api/...`

## 修复效果

### 修复前

```
访问：http://10.129.30.39:5000/client/room_remote.html
API地址：http://127.0.0.1:5000/api  ❌ 错误
结果：请求失败，无法操作
```

### 修复后

```
访问：http://10.129.30.39:5000/client/room_remote.html
API地址：http://10.129.30.39:5000/api  ✅ 正确
结果：请求成功，可以正常操作
```

## 兼容性

### 向后兼容

- ✅ 仍然支持URL参数手动指定
- ✅ 如果URL参数存在，优先使用参数值
- ✅ 如果没有参数，自动从当前URL构建

### 支持的场景

1. **同一台电脑**
   - `http://127.0.0.1:5000/client/room_remote.html` ✅
   - `http://localhost:5000/client/room_remote.html` ✅

2. **不同电脑（局域网）**
   - `http://10.129.30.39:5000/client/room_remote.html` ✅
   - `http://192.168.1.100:5000/client/room_remote.html` ✅

3. **自定义端口**
   - `http://10.129.30.39:8080/client/room_remote.html` ✅
   - 自动使用端口8080

## 调试信息

### 控制台输出

页面加载时会输出：
```javascript
API_BASE_URL: http://10.129.30.39:5000/api
```

### 网络请求

在Network标签页查看：
- 请求URL应该匹配当前页面的主机和端口
- 状态码应该是200（成功）

## 常见问题

### Q1: 仍然无法操作

**检查**：
1. 打开浏览器控制台（F12）
2. 查看Console标签页的错误信息
3. 查看Network标签页的请求状态
4. 确认API_BASE_URL是否正确

### Q2: API地址不正确

**检查**：
1. 查看控制台输出的 `API_BASE_URL`
2. 确认是否与当前页面URL匹配
3. 如果使用URL参数，检查参数格式

### Q3: 跨域问题

**解决**：
- 确保已安装并配置 `flask-cors`
- 参考 [CORS跨域配置说明.md](./CORS跨域配置说明.md)

## 修改的文件

- ✅ `client/room_remote.html` - 自动构建API地址
- ✅ `hotel/client/room_remote.html` - 同步更新

## 更新日期
2025年

## 相关文档
- [跨机器运行配置说明.md](./跨机器运行配置说明.md) - 网络配置
- [CORS跨域配置说明.md](./CORS跨域配置说明.md) - CORS配置

