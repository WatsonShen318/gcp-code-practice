# PA Caddie — Guided Review

FastAPI 读取 `data/case.json`，渲染基于 `pa_caddie_v4.html` 的交互界面。原始 HTML 保留用于参考，不直接提供为应用首页。无需前端构建和 npm 安装。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8081
```

打开 <http://127.0.0.1:8081>。修改 JSON 后刷新即可；修改 JS/CSS 后可用 Ctrl+F5 强制刷新。

## 文件和接口

- `app.py`：`GET /` 返回应用；`GET /api/case` 每次请求读取 JSON。
- `data/case.json`：schemaVersion 2，包含参考 HTML 的数据、57 个问题和跳转表。
- `static/index.html`、`styles.css`：参考 HTML 的结构、样式与响应式适配。
- `static/loader.js`：读取和检查 JSON，加载界面；失败时显示错误信息。
- `static/app.js`：问题路径、体重计算、药品编辑、历史/文档弹窗、备注和决定的页面状态。
- `pa_caddie_v4.html`：用户上传的原始参考文件，保留不改。

## 输入 JSON

| 字段 | 内容 |
| --- | --- |
| `schemaVersion` | 固定为 `2` |
| `cases` | 案件数组：`id`、`meta`、`member`、`claim`、`legs` |
| `cases[].legs` | 审核环节：角色、队列、初始答案 `initAns`、备注、文档等 |
| `skipLogic` | 问题编号 → `T`/`F` 的下一题编号或终点 `A`/`D` |
| `questionMetadata` | 每题的短标题 `s`、完整描述 `f`、证据、验证要求等 |
| `drugOptions` | Requested Drug 下拉菜单，label 和可选 ndc |
| `mockClaimDefaults` | 按案件 ID 配置表单默认值 |
| `mockClaimResults` | 按案件 ID 配置 Message/30/60/90 days 的示例响应 |
| `toolData` | 按案件 ID 配置 PA 历史和 claim 历史 |
| `caseNotes` | 保留原 HTML 的备注示例供参考；应用生成的备注使用当前答案和验证记录 |

答案使用 `T`（Yes）和 `F`（No）。原 HTML 仅要求人工确认 Q4，该行为已保留到问题元数据中。当前只有一个示例案件；添加多个案件后标题栏出现案件切换菜单，多审核环节显示 Leg 切换。

## 交互和输出

- 保留六步流程、动态问题路径、答案编辑、Cancel All、文档弹窗、体重计算器和结果确认。
- Q4 体重减重比例 = `(baseline - current) / baseline * 100`。输入必须为正且有限，使用未四舍五入的数值与 5% 比较。
- 修改答案、药品或计算器输入会撤销当前决定；更改计算器输入后必须再次点击 Use result。
- Denial 确认会记录 `deny`，不再误入 Approval。
- Run Mock Claim 读取并保留表单输入，显示 JSON 配置的示例响应及结果标签页，不调用真实理赔服务；输入不会驱动真实药房规则计算。
- Generate Notes 使用当前答案、实际人工验证状态和计算器结果，不写入未经验证的“documentation verified”。
- 顶部 **Export JSON** 下载当前案件和审核环节的结果，含答案、路径、分数、验证记录、体重、Mock Claim 输入/示例响应、Notes 和决定快照。
- 所有决定均为本地演示，不会发送给外部系统。除 Urgent 保存在浏览器 localStorage 外，刷新会重置编辑；需要保留结果请先导出。
- Member Search 仅在当前案件会员中匹配姓名或 ID；PA/Claim 历史显示已加载的 JSON 数据。

输出 JSON 与输入配置 JSON 用途不同：导出文件是审核结果快照，不能直接替换 `data/case.json`。当前没有服务端写回、结果导入或数据库。

## 验证

```powershell
python -m unittest -v
node --test tests/workflow.test.cjs
```

前者验证 FastAPI 页面、资源和 JSON 接口，后者验证问题跳转、验证门槛、Approval/Denial、状态失效、输入快照和文本转义。Node.js 只在运行这些规则测试时需要。

Dockerfile 已包含 static 和 data。本次只修改代码并推送，不自动部署 Cloud Run。
