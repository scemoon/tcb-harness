# Native UI 规范 — iOS & Android

React Native 跨平台 UI 规范。

## 技术栈

| 平台 | 框架 | UI 库 | 状态管理 |
|------|------|-------|----------|
| iOS | React Native | SwiftUI-style Components | Zustand / Redux Toolkit |
| Android | React Native | Material Design 3 | Zustand / Redux Toolkit |
| 跨平台 | - | React Native Paper | - |

## 设计系统

| 平台 | 设计语言 | 设计库 |
|------|----------|--------|
| iOS | Human Interface Guidelines (HIG) | SwiftUI / UIKit |
| Android | Material Design 3 | Material You |
| React Native | 跨平台统一 | React Native Paper |

## iOS 设计规范

### 安全区域 (Safe Area)

```tsx
import { SafeAreaView } from 'react-native';

<SafeAreaView className="flex-1 bg-white">
  {/* 内容 */}
</SafeAreaView>
```

| 区域 | 说明 |
|------|------|
| Top | status bar, notch, Dynamic Island |
| Bottom | home indicator |

### 字体 (SF Pro)

| 样式 | 字重 | 字号 | 行高 |
|------|------|------|------|
| Large Title | Bold | 34px | 41px |
| Title 1 | Bold | 28px | 34px |
| Title 2 | Bold | 22px | 28px |
| Title 3 | Semibold | 20px | 25px |
| Headline | Semibold | 17px | 22px |
| Body | Regular | 17px | 22px |
| Callout | Regular | 16px | 21px |
| Subhead | Regular | 15px | 20px |
| Footnote | Regular | 13px | 18px |
| Caption 1 | Regular | 12px | 16px |
| Caption 2 | Regular | 11px | 13px |

### iOS 颜色

```typescript
const iOSColors = {
  // 系统色
  systemBlue: '#007AFF',
  systemGreen: '#34C759',
  systemRed: '#FF3B30',
  systemOrange: '#FF9500',
  systemYellow: '#FFCC00',
  systemPink: '#FF2D55',
  systemPurple: '#AF52DE',
  systemTeal: '#5AC8FA',
  systemIndigo: '#5856D6',

  // 背景色
  systemBackground: '#FFFFFF',
  secondarySystemBackground: '#F2F2F7',
  tertiarySystemBackground: '#FFFFFF',
  systemGroupedBackground: '#F2F2F7',

  // 文字色
  label: '#000000',
  secondaryLabel: 'rgba(60, 60, 67, 0.6)',
  tertiaryLabel: 'rgba(60, 60, 67, 0.3)',

  // 分隔线
  separator: 'rgba(60, 60, 67, 0.29)',
};
```

## Android 设计规范

### Material Design 3

```tsx
import { MD3LightTheme, MD3DarkTheme } from 'react-native-paper';

const lightTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: '#0066CC',
    secondary: '#6B6B6B',
    error: '#BA1A1A',
    background: '#FFFBFE',
    surface: '#FFFBFE',
  },
};
```

### 字体 (Roboto)

| 样式 | 字重 | 字号 | 行高 |
|------|------|------|------|
| Display Large | Regular | 57px | 64px |
| Display Medium | Regular | 45px | 52px |
| Display Small | Regular | 36px | 44px |
| Headline Large | Regular | 32px | 40px |
| Headline Medium | Regular | 28px | 36px |
| Headline Small | Regular | 24px | 32px |
| Title Large | Medium | 22px | 28px |
| Title Medium | Medium | 16px | 24px |
| Title Small | Medium | 14px | 20px |
| Body Large | Regular | 16px | 24px |
| Body Medium | Regular | 14px | 20px |
| Body Small | Regular | 12px | 16px |
| Label Large | Medium | 14px | 20px |
| Label Medium | Medium | 12px | 16px |
| Label Small | Medium | 11px | 16px |

### Android 颜色

```typescript
const MaterialColors = {
  primary: '#0066CC',
  onPrimary: '#FFFFFF',
  primaryContainer: '#D3E4FF',
  onPrimaryContainer: '#001D36',

  secondary: '#6B6B6B',
  onSecondary: '#FFFFFF',
  secondaryContainer: '#E5E0EC',
  onSecondaryContainer: '#1D1B20',

  tertiary: '#785900',
  onTertiary: '#FFFFFF',
  tertiaryContainer: '#FFDEA6',
  onTertiaryContainer: '#261A00',

  error: '#BA1A1A',
  onError: '#FFFFFF',
  errorContainer: '#FFDAD6',
  onErrorContainer: '#410002',

  background: '#FFFBFE',
  onBackground: '#1C1B1E',
  surface: '#FFFBFE',
  onSurface: '#1C1B1E',
  surfaceVariant: '#E7E0EC',
  onSurfaceVariant: '#49454E',

  outline: '#79747E',
  outlineVariant: '#CAC4D0',
};
```

## 跨平台组件规范

### 1. Button

```tsx
interface ButtonProps {
  variant: 'filled' | 'outlined' | 'text' | 'elevated';
  size: 'small' | 'medium' | 'large';
  disabled?: boolean;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  onPress: () => void;
  children: ReactNode;
}
```

| 平台 | 样式 | 最小尺寸 |
|------|------|----------|
| iOS | 系统风格，圆角 10px | 44x44px |
| Android | Material 3，圆角 20px (full width rounded) | 48x48px |

### 2. Input

```tsx
interface InputProps {
  label: string;
  placeholder?: string;
  value: string;
  onChangeText: (text: string) => void;
  error?: string;
  disabled?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  secureTextEntry?: boolean;
}
```

| 平台 | 样式 |
|------|------|
| iOS | SF Pro 风格，下划线或圆角背景 |
| Android | Material 3 OutlinedBox |

### 3. Card

```tsx
interface CardProps {
  variant: 'elevated' | 'outlined' | 'filled';
  children: ReactNode;
  onPress?: () => void;
}
```

| 平台 | 样式 |
|------|------|
| iOS | 白色背景，轻阴影，圆角 12px |
| Android | Material 3 ElevatedCard |

### 4. Navigation

```tsx
// Stack Navigator
<Stack.Navigator>
  <Stack.Screen name="Home" component={HomeScreen} />
  <Stack.Screen name="Detail" component={DetailScreen} />
</Stack.Navigator>

// Tab Navigator
<Tab.Navigator>
  <Tab.Screen name="Home" component={HomeScreen} />
  <Tab.Screen name="Profile" component={ProfileScreen} />
</Tab.Navigator>
```

| 平台 | Tab Bar 样式 |
|------|--------------|
| iOS | 底部 Tab Bar，SF Symbols 图标 |
| Android | 底部 Navigation Bar，Material Icons |

## 状态处理

### Loading 状态

```tsx
// iOS
<ActivityIndicator size="large" color="#007AFF" />

// Android
<CircularProgressIndicator />

// 统一 LoadingOverlay
<LoadingOverlay visible={isLoading} />
```

### Empty State

```tsx
<EmptyState
  icon={<IllustrationNoData />}
  title="暂无数据"
  description="稍后再试"
  action={<Button>刷新</Button>}
/>
```

### Error State

```tsx
<ErrorState
  icon={<IllustrationError />}
  title="加载失败"
  description="请检查网络连接"
  action={<Button onPress={retry}>重试</Button>}
/>
```

## 平台检测

```typescript
import { Platform, StatusBar } from 'react-native';

// 平台检测
const isIOS = Platform.OS === 'ios';
const isAndroid = Platform.OS === 'android';

// 平台特定样式
const containerStyle = {
  ...(Platform.OS === 'ios'
    ? { paddingTop: 50 }
    : { paddingTop: StatusBar.currentHeight }),
};

// 平台特定组件
{Platform.OS === 'ios' ? (
  <IOSPicker />
) : (
  <AndroidPicker />
)}
```

## 手势与交互

### iOS

| 手势 | 行为 |
|------|------|
| Swipe from left | 返回上一页 |
| Pull to refresh | 下拉刷新 |
| Long press | Context menu |

### Android

| 手势 | 行为 |
|------|------|
| Swipe from left edge | 返回 |
| Long press | 选择/Context menu |
| Double tap | 缩放 |

## 评审清单

- [ ] iOS 使用 SafeAreaView
- [ ] iOS 使用 SF Pro 字体，Android 使用 Roboto
- [ ] iOS 使用系统蓝 (#007AFF)，Android 使用 Material 3 primary
- [ ] 所有点击目标 ≥ 44x44dp
- [ ] 支持深色模式
- [ ] 处理键盘遮挡输入框
- [ ] 支持系统字体缩放
- [ ] 处理网络状态变化
