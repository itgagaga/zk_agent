# 前端页面素材图 / 图标开源项目推荐

这份清单适合用于前端项目页面美化，尤其是页面看起来比较单调、空白、缺少视觉元素时。推荐优先使用 SVG 素材，因为 SVG 可以自由缩放、改颜色，也更容易和项目主题色统一。

---

## 一、开源素材项目清单

| 分类 | 项目 | 推荐原因 | 适合放在哪 |
|---|---|---|---|
| 通用图标 | [Tabler Icons](https://github.com/tabler/tabler-icons) | 6000+ SVG 图标，MIT License，风格统一，特别适合后台系统和 Dashboard。 | 侧边栏、按钮、卡片、表格操作 |
| 通用图标 | [Lucide](https://github.com/lucide-icons/lucide) | Feather 风格的开源图标库，简洁现代，适合 Web App。 | 导航、设置页、功能入口 |
| Tailwind 图标 | [Heroicons](https://github.com/tailwindlabs/heroicons) | Tailwind Labs 出品，MIT License，和 Tailwind 项目非常搭。 | 表单、按钮、提示、菜单 |
| 多端图标 | [Iconoir](https://github.com/iconoir-icons/iconoir) | MIT License，支持 React、Vue、Flutter、Figma 等，适合跨端项目。 | Web、移动端、设计稿统一 |
| 品牌 Logo | [Simple Icons](https://github.com/simple-icons/simple-icons) | 收录大量品牌 SVG 图标，适合展示技术栈或第三方平台。 | 技术栈、登录方式、合作方展示 |
| 技术栈图标 | [Devicon](https://github.com/devicons/devicon) | 专门收录编程语言、开发工具、设计工具图标。 | 项目介绍页、个人作品集、技术栈模块 |
| 空状态插画 | [Open Doodles](https://www.opendoodles.com/) | CC0 授权，可复制、编辑、混合、重绘，手绘风适合让页面更轻松。 | 空列表、欢迎页、引导页 |
| 人物插画 | [Open Peeps](https://www.openpeeps.com/) | 公共领域 CC0，适合拼人物、用户画像、团队场景。 | 用户页、团队页、Persona、空状态 |
| 现代插画 | [IRA Design](https://iradesign.io/) | 免费插画组件，偏渐变、现代产品风。 | 官网 Hero、产品介绍、功能说明 |
| Tailwind 插画 | [Flowbite Illustrations](https://flowbite.com/illustrations/) | 免费开源 SVG 插画，和 Tailwind / Flowbite 生态搭配舒服。 | SaaS 页面、空状态、功能区 |
| 加载动画 | [svg-spinners](https://github.com/n3r4zzurr0/svg-spinners) | 一组 SVG loading 动画，适合直接用于按钮加载、页面加载。 | Loading、按钮提交、异步请求 |
| 手绘流程图 | [Excalidraw](https://github.com/excalidraw/excalidraw) | MIT License，可画手绘风流程图、架构图、说明图，再导出 SVG/PNG。 | 架构说明、流程图、帮助文档 |

---

## 二、推荐搭配方案

### 1. 后台管理系统 / Dashboard

推荐组合：

- Tabler Icons
- Flowbite Illustrations
- svg-spinners

适合场景：

- 数据看板
- 管理后台
- 工具类系统
- 表格、筛选、统计卡片较多的页面

这套组合比较稳，图标风格统一，页面不会太花，同时能补充空状态、加载状态和功能入口的视觉细节。

---

### 2. 个人作品集 / 毕设 / 开源项目主页

推荐组合：

- Open Doodles
- Devicon
- Lucide

适合场景：

- 个人主页
- 项目介绍页
- 毕设展示页
- GitHub 项目官网

Open Doodles 可以增加轻松的手绘氛围，Devicon 用来展示技术栈，Lucide 用作功能图标，整体会比较年轻、清爽。

---

### 3. SaaS 官网 / 产品展示页

推荐组合：

- IRA Design
- Heroicons
- Simple Icons

适合场景：

- 产品官网
- SaaS Landing Page
- 功能介绍页
- 集成平台展示页

Hero 区可以放 IRA Design 插画，功能区使用 Heroicons，技术生态或合作平台区域使用 Simple Icons，整体会更像成熟的产品官网。

---

## 三、页面中可以重点补充素材的位置

如果页面目前太单调，可以优先从这些地方加素材：

### 1. 首页 Hero 区

可以加入一张主视觉插画，例如：

- 产品功能插画
- 数据分析插画
- 团队协作插画
- 开发者工作流插画

推荐使用：

- IRA Design
- Open Doodles
- Flowbite Illustrations

---

### 2. 空状态页面

例如：

- 暂无数据
- 暂无订单
- 暂无消息
- 搜索无结果
- 页面加载失败

推荐使用：

- Open Doodles
- Open Peeps
- Flowbite Illustrations

---

### 3. 功能卡片

每个功能卡片前面放一个小图标，可以让页面更有层次。

推荐使用：

- Tabler Icons
- Lucide
- Heroicons
- Iconoir

---

### 4. 技术栈展示区

如果是个人项目、毕业设计、开源项目，可以展示技术栈图标。

推荐使用：

- Devicon
- Simple Icons

---

### 5. 加载状态

不要只用纯文字“加载中”，可以放一个 SVG loading 动画。

推荐使用：

- svg-spinners
- lottie-web
- dotlottie-web

---

## 四、使用建议

### 1. 优先使用 SVG

SVG 的好处：

- 缩放不失真
- 文件体积通常比较小
- 可以直接修改颜色
- 可以用 CSS 控制样式
- 更容易适配深色模式和浅色模式

---

### 2. 一个项目不要混太多图标库

建议一个项目主用一个图标库：

- 后台系统：Tabler Icons 或 Lucide
- Tailwind 项目：Heroicons
- 多端项目：Iconoir
- 技术栈展示：Devicon / Simple Icons

图标风格混太多，页面会显得杂乱。

---

### 3. 插画颜色尽量跟主题色统一

如果项目主色是蓝色、紫色、绿色等，插画也尽量改成接近的颜色。  
这样页面看起来会更像一个完整的产品，而不是简单拼素材。

---

### 4. 正式项目要看 License

放进正式项目之前，建议查看每个仓库的 `LICENSE` 文件。

常见授权说明：

- MIT：通常比较宽松，可商用，可修改。
- CC0：接近公共领域，通常使用限制很少。
- CC BY：通常需要署名。
- CC BY-SA：通常需要署名，并且可能要求相同方式共享。
- 品牌 Logo：即使图标库开源，也需要注意对应品牌的商标使用规范。

---

## 五、优先推荐收藏的项目

如果只想先收藏几个最实用的，可以优先看这些：

1. [Tabler Icons](https://github.com/tabler/tabler-icons)
2. [Lucide](https://github.com/lucide-icons/lucide)
3. [Heroicons](https://github.com/tailwindlabs/heroicons)
4. [Devicon](https://github.com/devicons/devicon)
5. [Simple Icons](https://github.com/simple-icons/simple-icons)
6. [Open Doodles](https://www.opendoodles.com/)
7. [Open Peeps](https://www.openpeeps.com/)
8. [IRA Design](https://iradesign.io/)
9. [Flowbite Illustrations](https://flowbite.com/illustrations/)
10. [svg-spinners](https://github.com/n3r4zzurr0/svg-spinners)
11. [Excalidraw](https://github.com/excalidraw/excalidraw)

---

## 六、简单落地思路

可以按照下面这个顺序优化页面：

1. 给导航、按钮、卡片加统一图标。
2. 给首页或欢迎页加一张主视觉插画。
3. 给暂无数据、搜索为空、加载失败等状态加空状态插画。
4. 给加载、提交、上传等过程加 SVG loading 动画。
5. 给项目介绍页加技术栈图标。
6. 统一所有素材的颜色，让它们贴近项目主题色。

这样不需要大改页面结构，也能明显提升前端页面的完成度。
