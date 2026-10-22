# PA Caddie — Guided Review

FastAPI 读取本地 JSON，前端按参考截图展示审核页面。不需要 Node.js 或前端构建步骤。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8080
```

打开 <http://localhost:8080>。

## 数据与页面

- `data/case.json`：示例数据。修改并保存后刷新页面即可，不需要重启服务。
- `app.py`：`GET /` 返回页面，`GET /api/case` 每次读取 JSON。
- `static/index.html`：页面结构。
- `static/styles.css`：布局、状态颜色和移动端适配。
- `static/app.js`：获取 JSON，调用 `renderCase(data)` 渲染，通过文本节点展示数据。

JSON 字段：

| 字段 | 用途 |
| --- | --- |
| `paNumber`, `drug`, `lineOfBusiness`, `origin` | 顶部案件摘要 |
| `role`, `queue` | 标题栏 |
| `member` | 会员信息对象，键作为标签、值作为文字 |
| `pa.pac`, `pa.psg`, `pa.urgent` | 左侧 PA 信息，紧急状态只读 |
| `steps` | 按数组顺序生成审核卡片 |
| `steps[].title`, `status` | 步骤标题、状态文字 |
| `steps[].state` | `complete` 绿色、`review` 黄色、`pending` 灰色 |
| `steps[].content` | 可选的展开说明文字 |

步骤支持展开/收起，展开区域和表单由 JSON 配置。Member Center 按钮暂未接入功能。页面中的案件和状态均为示例，不执行审核或保存操作。

## 验证

```powershell
python -m unittest -v
```

Dockerfile 已包含页面资源和 JSON 文件。现有 `deploy.ps1` 可用于后续部署，本次仅本地运行。

## 展开区域（JSON 配置）

`steps[].type` 决定渲染的区域，分别对应同名顶层对象：

- `drugVerification`：提交药名、NDC、GPI、说明和 `requestedDrugOptions` 下拉选项。
- `paHistory`：汇总说明、`records` 历史表格。
- `mockClaim`：结果文案、表单默认值，以及 `productSelectionOptions`（value/label）。Run Mock Claim 仅展示 JSON 中的示例结果，不调用药房或理赔系统。
- `criteriaReview`：标题、提示、`questions`（id/label/answer/status/state/detail）和 `result`。Edit 可临时修改答案，不计算审核结果，也不更改验证状态。
- `notes`：默认 text、maxLength、placeholder、generatedText。Generate Notes 使用 JSON 中的预设文字。
- `caseDecision`：等待验证的说明文字。

所有表单改动只保留在当前页面内，刷新后重新读取 JSON，没有写回服务器。截图没有展示 Q3、完整 Q4 或下拉备选值，示例中已标注或仅保留截图中的选项，可直接在 JSON 中补齐。
