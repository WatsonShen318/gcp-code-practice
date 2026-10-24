# PA Caddie — Guided Review

FastAPI 读取 `data/case.json`，渲染基于 `pa_caddie_v4.html` 的交互界面。原始 HTML 保留用于参考，不直接提供为应用首页。无需前端构建和 npm 安装。

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8081
```

打开 <http://127.0.0.1:8081>。修改 JSON 后刷新即可；修改 JS/CSS 后可用 Ctrl+F5 强制刷新。

## 文件和接口

- `app.py`：`GET /` 返回应用；`GET /api/case` 每次请求读取 JSON；`GET /health` 返回 HTTP 200 和 `{"status":"ok"}`，供 CI/CD 和 GKE 健康检查使用。
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

## Shared GKE 镜像

Dockerfile 使用组织的 builder 和 distroless 镜像，在 builder 的 `/build` 放应用文件、`/app/packages` 放 Python 依赖。最终阶段分别将应用、static、data 复制到 `/app`，并显式指定 `--app-dir /app`。构建阶段增加应用导入检查。

镜像默认监听 `8000`；Deployment、Service 的 targetPort 和探针需要与此一致。共享集群若在 Deployment 中配置了 command/args，它们会覆盖镜像默认入口；请确认仍使用 `python -m uvicorn app:app --app-dir /app --host 0.0.0.0 --port 8000`，且 volumeMount 不覆盖 `/app`。

修改 Dockerfile 后需要重新构建并发布新镜像，再更新 Deployment 使用的镜像版本。仅重启使用旧镜像的 Pod 不会包含修复。组织私有基础镜像和集群需要在具备访问权限的环境中验证；仓库的本地测试不能替代最终镜像运行测试。

## 邮箱与 AD Group 访问限制（独立于 SAGE）

`access_control.py` 仅复用参考文件中的身份提取思路：公司 OAuth 登录后，读取经过签名验证的 access token 中的 `mail`/`email` 和 `groups`/`Groups`/`GROUPS`，需要时从公司 userinfo 接口补充。支持普通组名和 LDAP `CN=...`。不导入 `config.py` / `reference_email.py`，不使用 SAGE Cookie、应用权限映射、Spanner 或参考配置中的密钥。

默认允许截图中的 11 个完整组名，任意一个匹配即可：

```text
app-paops-eng
app-paops-pnp-eng
app-paops-prod-eng
app-paops-restrict-admin
app-paops-restrict-eng
app-paops-rnp-admin
app-paops-rnp-eng
clb-paops-rnp-editor
clb-paops-rnp-read
csm-paops-pnp-read
csm-paops-rnp-read
```

匹配忽略大小写，使用完整组名，不按 `paops` 前缀放行。可用 `AUTH_ALLOWED_GROUPS`（逗号分隔）覆盖。上游必须返回这些组的组名或 LDAP CN；若上游只返回 Object ID，需要将允许列表改为完整 Object ID。本实现不会通过邮箱查目录，也不根据邮箱域名放行；组未返回或无法校验时拒绝访问。

### 部署配置

参考 `.env.example`，在 GKE 环境变量/Secret 中设置：

- `AUTH_ENABLED=true`：启用限制。Docker 最终镜像默认开启；本机未设置时默认关闭，方便继续本地测试。开启但配置不全会拒绝启动，不会自动放行。
- `SSO_CLIENT_ID`、`SSO_CLIENT_SECRET`：获授权用于本应用的公司 OAuth Client；不自动复用 SAGE 凭据。
- `SSO_AUTHORIZE_URL`、`SSO_TOKEN_URL`、`SSO_USERINFO_URL`：公司认证端点。
- `SSO_ISSUER`、`SSO_JWKS_URL`、`SSO_AUDIENCE`：access token 的发行方、签名公钥地址和预期 audience，用于 RS256 签名、发行方、受众、有效期验证。参考文件未包含完整的签名校验配置，需由平台提供。
- `SSO_REDIRECT_URI=https://你的应用域名/auth/callback`：必须与公司 OAuth Client 注册的回调地址一致。
- `AUTH_SESSION_SECRET`：本应用独立的随机密钥，至少 32 字符，放入 GKE Secret；所有副本使用相同值。

代码不会自动加载 `.env.example`，不要提交真实密钥。正式环境使用 HTTPS；反向代理应保留本应用的根路径 `/auth/callback`，不要缓存应用内容。所有 Pod 必须共享相同会话密钥，才能处理负载均衡后的登录回调。

### 访问与日志

1. 未登录访问 `/` → `/auth/login` → 公司登录。已有公司会话时是否静默通过由公司认证服务决定。
2. `/auth/callback` 交换并验证 Token，读取邮箱和组。Authlib 管理随机 state、nonce 和 PKCE。
3. 命中允许组 → 设置本应用的 Secure/HttpOnly Cookie → 跳转 `/`；不命中 → **403**。
4. 页面、静态资源、JSON 数据接口和 API 文档均受后端保护；未认证直接访问数据接口返回 **401**。
5. `/health` 继续免登录返回 **200**，不影响集群探针。

应用日志为 `access_check` JSON，记录时间、邮箱、允许/拒绝、原因和命中组，不输出 Token、Secret 或完整组列表；无法确认身份的请求 email 为 null。Uvicorn callback access log 会去除含授权 code 的查询参数；Ingress/外部日志由平台另行配置。

会话最长 15 分钟且不超过 access token 有效期。组成员变更将在现有会话过期并重新登录后反映，不是实时目录查询。浏览器回调和签名测试使用模拟 SSO；生产激活仍需要上述配置以及公司端点的连通性、Client 回调登记和组声明授权。
