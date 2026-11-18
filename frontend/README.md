# 前端（Next.js）

客经 AI 审核工具的经理端界面。用 Next.js App Router + TypeScript + Tailwind，不含服务端业务逻辑，所有数据来自 `../backend`。

## 启动

```bash
npm install
cp .env.example .env.local     # 本地开发保持默认即可
npm run dev                    # http://localhost:3000
```

后端要先起来（默认 `http://127.0.0.1:8000`），否则页面会显示加载失败。

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | 后端地址 |
| `NEXT_PUBLIC_API_TOKEN` | 必须与后端 `APP_AUTH_TOKEN` 一致；本地开发可都留空（后端只允许本机访问） |

## 页面

| 路由 | 作用 |
| --- | --- |
| `/` | 首页入口 |
| `/import` | 上传拜访 Excel、批量上传录音、确认门店与录音的关联、提交批次 |
| `/review` | 审核任务列表，按批次/状态筛选、排序、导出全部 |
| `/review/[taskId]` | 审核详情：四个业务模块、47 个字段、录音播放器、转写原文、逐字段改值与填原因、存草稿、提交 |

审核详情页按「去年销售额 / 今年截至上月销售额 / 畅销品牌 / 其他问题」四模块组织。去年与今年销售额按马爹利、轩尼诗、人头马、白酒、威士忌顺序排列；畅销产品把名称、进货价、上月零售瓶数合成一组。

## 与后端约定

- 所有业务接口都要令牌。`src/lib/api.ts` 的 `apiRequest()` 自动带上 `X-API-Token`，并对 204 做了处理（删除接口返回空体，按 JSON 解析会炸）。
- **导出按钮不能用 `<a href>`**：浏览器发不出自定义请求头，必然 401。统一用 `downloadFile()`（fetch + blob）。
- **音频 `src` 是唯一允许 `?token=` 的地方**：`<audio>` 没法加请求头，所以后端录音接口额外接受查询参数令牌。
- 后端字段名用 `serialization_alias` 转成驼峰，前端类型在 `src/lib/review-data.ts` 手写维护，两边没有自动校验。

## 开发注意

- `src/app/review/[taskId]/review-detail.tsx` 目前 300+ 行，JSX 里有单行超 3000 字符的表达式，改起来很痛苦。要动这块建议先拆成 `AudioPanel` / `TranscriptPanel` / `FieldTable` 三个组件。
- 没有配置测试框架，改 47 字段表格联动、状态机、原因必填这些交互全靠手点。加 `vitest` + `playwright` 是值得的。
- 提交前跑一遍：

  ```bash
  npm run lint
  npx tsc --noEmit
  ```
