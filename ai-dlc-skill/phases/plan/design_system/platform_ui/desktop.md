# Desktop UI 规范 — Electron & Tauri

桌面端 UI 规范，支持 macOS / Windows / Linux。

## 技术栈

| 框架 | 渲染引擎 | UI 方案 |
|------|----------|---------|
| **Electron** | Chromium | React + Tailwind / Ant Design |
| **Tauri** | WebView (系统) | React + Tailwind |

## 窗口规范

### 最小窗口尺寸

```typescript
// main window config
const mainWindowConfig = {
  minWidth: 1024,
  minHeight: 600,
  defaultWidth: 1280,
  defaultHeight: 800,
};
```

| 场景 | 最小尺寸 | 推荐尺寸 |
|------|----------|----------|
| 通用应用 | 1024x600 | 1280x800 |
| 复杂工具 | 1280x720 | 1440x900 |
| 全屏应用 | 1920x1080 | - |

### 窗口边框

| 平台 | 窗口框架 |
|------|----------|
| macOS | 使用原生标题栏 (traffic lights) |
| Windows | 使用原生标题栏或自定义 |
| Linux | 使用原生标题栏 |

### 窗口状态

```typescript
interface WindowState {
  isMaximized: boolean;
  isMinimized: boolean;
  isFullScreen: boolean;
  bounds: { x: number; y: number; width: number; height: number };
}
```

## 原生菜单 (Native Menu)

### macOS 菜单结构

```typescript
// Electron
const template: MenuItemConstructorOptions[] = [
  {
    label: 'App Name',
    submenu: [
      { label: 'About', role: 'about' },
      { type: 'separator' },
      { label: 'Preferences', accelerator: 'Cmd+,', click: () => {} },
      { type: 'separator' },
      { label: 'Quit', accelerator: 'Cmd+Q', role: 'quit' },
    ],
  },
  {
    label: 'File',
    submenu: [
      { label: 'New', accelerator: 'Cmd+N', click: () => {} },
      { label: 'Open', accelerator: 'Cmd+O', click: () => {} },
      { type: 'separator' },
      { label: 'Save', accelerator: 'Cmd+S', click: () => {} },
    ],
  },
  {
    label: 'Edit',
    submenu: [
      { label: 'Undo', accelerator: 'Cmd+Z', role: 'undo' },
      { label: 'Redo', accelerator: 'Cmd+Shift+Z', role: 'redo' },
      { type: 'separator' },
      { label: 'Cut', accelerator: 'Cmd+X', role: 'cut' },
      { label: 'Copy', accelerator: 'Cmd+C', role: 'copy' },
      { label: 'Paste', accelerator: 'Cmd+V', role: 'paste' },
    ],
  },
  {
    label: 'View',
    submenu: [
      { label: 'Reload', accelerator: 'Cmd+R', role: 'reload' },
      { label: 'Toggle DevTools', accelerator: 'Cmd+Alt+I', role: 'toggleDevTools' },
      { type: 'separator' },
      { label: 'Actual Size', accelerator: 'Cmd+0', role: 'resetZoom' },
      { label: 'Zoom In', accelerator: 'Cmd+=', role: 'zoomIn' },
      { label: 'Zoom Out', accelerator: 'Cmd+-', role: 'zoomOut' },
      { type: 'separator' },
      { label: 'Toggle Fullscreen', accelerator: 'Cmd+Ctrl+F', role: 'togglefullscreen' },
    ],
  },
  {
    label: 'Window',
    submenu: [
      { label: 'Minimize', accelerator: 'Cmd+M', role: 'minimize' },
      { label: 'Maximize', click: () => {} },
      { type: 'separator' },
      { label: 'Close', accelerator: 'Cmd+W', role: 'close' },
    ],
  },
];
```

### Tauri 菜单

```rust
// src-tauri/src/main.rs
use tauri::MenuBuilder;

let menu = MenuBuilder::new(app)
  .item(&MenuItem::new("About", true, None::<&str>))
  .separator()
  .item(&MenuItem::new("Preferences", true, Some("CmdOrCtrl+,")))
  .separator()
  .item(&MenuItem::new("Quit", true, Some("CmdOrCtrl+Q")))
  .build()?;
```

## 快捷键规范

### 全局快捷键

| 快捷键 | macOS | Windows/Linux | 功能 |
|--------|-------|---------------|------|
| 新建 | Cmd+N | Ctrl+N | 新建 |
| 打开 | Cmd+O | Ctrl+O | 打开 |
| 保存 | Cmd+S | Ctrl+S | 保存 |
| 关闭 | Cmd+W | Ctrl+W | 关闭当前 |
| 退出 | Cmd+Q | Alt+F4 | 退出应用 |
| 撤销 | Cmd+Z | Ctrl+Z | 撤销 |
| 重做 | Cmd+Shift+Z | Ctrl+Y | 重做 |
| 复制 | Cmd+C | Ctrl+C | 复制 |
| 粘贴 | Cmd+V | Ctrl+V | 粘贴 |
| 全选 | Cmd+A | Ctrl+A | 全选 |
| 查找 | Cmd+F | Ctrl+F | 查找 |
| 设置 | Cmd+, | Ctrl+, | 偏好设置 |

### 应用内快捷键

| 快捷键 | 功能 |
|--------|------|
| Cmd+1~9 | 切换 Tab |
| Cmd+[ | 后退 |
| Cmd+] | 前进 |
| Cmd++ | 放大 |
| Cmd+- | 缩小 |
| Cmd+0 | 实际大小 |

## 系统托盘 (System Tray)

### Electron Tray

```typescript
// main process
import { Tray, Menu, nativeImage } from 'electron';

const tray = new Tray(nativeImage.createFromPath('icon.png'));

const contextMenu = Menu.buildFromTemplate([
  { label: 'Show', click: () => mainWindow.show() },
  { label: 'Quit', click: () => app.quit() },
]);

tray.setContextMenu(contextMenu);
tray.setToolTip('App Name');
```

### 托盘图标尺寸

| 平台 | 图标尺寸 |
|------|----------|
| macOS | 22x22 (template image) |
| Windows | 16x16, 32x32 |
| Linux | 22x22 |

## 拖拽区域 (Drag Region)

### 自定义标题栏拖拽

```css
/* 拖拽区域样式 */
.titlebar-drag-region {
  -webkit-app-region: drag;
  app-region: drag;
}

/* 排除按钮 */
.titlebar-button {
  -webkit-app-region: no-drag;
  app-region: no-drag;
}
```

```tsx
// React
<div className="titlebar-drag-region">
  <span className="title">App Name</span>
  <div className="titlebar-buttons">
    <button className="titlebar-button" onClick={handleMinimize}>-</button>
    <button className="titlebar-button" onClick={handleMaximize}>+</button>
    <button className="titlebar-button" onClick={handleClose}>x</button>
  </div>
</div>
```

## 上下文菜单 (Context Menu)

```typescript
// Electron
const contextMenu = Menu.buildFromTemplate([
  { label: 'Cut', accelerator: 'Cmd+X', role: 'cut' },
  { label: 'Copy', accelerator: 'Cmd+C', role: 'copy' },
  { label: 'Paste', accelerator: 'Cmd+V', role: 'paste' },
  { type: 'separator' },
  { label: 'Select All', accelerator: 'Cmd+A', role: 'selectAll' },
]);

window.addContextMenuListener((event) => {
  event.preventDefault();
  contextMenu.popup();
});
```

## 通知 (Notifications)

```typescript
// Electron
new Notification({
  title: 'New Message',
  body: 'You have a new message from John',
  icon: 'icon.png',
  silent: false,
}).show();
```

## 自动更新

```typescript
// Electron
import { autoUpdater } from 'electron-updater';

autoUpdater.on('update-available', () => {
  // 显示更新提示
});

autoUpdater.on('update-downloaded', () => {
  // 提示用户重启安装
});

autoUpdater.checkForUpdates();
```

## 文件对话框

```typescript
// 打开文件
const result = await dialog.showOpenDialog({
  properties: ['openFile'],
  filters: [
    { name: 'Images', extensions: ['jpg', 'png', 'gif'] },
    { name: 'All Files', extensions: ['*'] },
  ],
});

// 保存文件
const result = await dialog.showSaveDialog({
  defaultPath: 'untitled.txt',
  filters: [
    { name: 'Text', extensions: ['txt'] },
  ],
});
```

## 窗口间通信 (IPC)

```typescript
// main.ts
ipcMain.handle('get-user-data', async () => {
  return await fetchUserData();
});

// renderer.ts
const userData = await window.electronAPI.getUserData();
```

## 暗色模式

```typescript
// 监听系统主题变化
const { nativeTheme } = require('electron');

nativeTheme.on('updated', () => {
  document.documentElement.dataset.theme = nativeTheme.shouldUseDarkColors ? 'dark' : 'light';
});
```

## 评审清单

- [ ] 最小窗口尺寸 ≥ 1024x600
- [ ] 原生菜单完整 (File/Edit/View/Window/Help)
- [ ] 全局快捷键不冲突
- [ ] 支持系统托盘
- [ ] 支持上下文菜单
- [ ] 支持文件对话框
- [ ] 支持拖拽文件到窗口
- [ ] 支持深色模式
- [ ] 支持自动更新
- [ ] macOS traffic lights 可用
- [ ] 窗口状态持久化
