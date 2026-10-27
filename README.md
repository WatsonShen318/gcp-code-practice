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

## Ping userinfo 与 AD Group 访问限制

采用 PA Pulse 参考中的方法：公司 Ping 登录 → 用授权 code 换取 access token → 调用 HTTPS userinfo → 获取邮箱与 AD Group → 匹配允许组。access token 视为不透明字符串，不再要求它是 JWT，也不需要旧版的 Issuer/JWKS/Audience 配置。已删除旧认证模块、三个参考 ZIP、SAGE config 和 reference_email.py；应用界面与业务 JSON 保持不变。

`ping_auth.py` 合并 userinfo 的 `groups_cn` 和 `groups`；支持字符串、数组及 LDAP `CN=...`。匹配完整组名并忽略大小写，任意一个匹配即可：

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

允许组为空、缺失或不匹配不会放行。这里没有参考项目“空允许列表即放行”的行为，也没有测试登录旁路。如果上游只返回组 Object ID，必须先调整允许名单；目前采用图片中的组名。群组查询来源始终是 Ping userinfo，不是根据用户输入的邮箱查询或放行。

### 部署参数

示例见 `.env.example`。配置方式是 GKE 的环境变量/Secret，不会自动加载示例文件：

| 配置 | 用途 |
| --- | --- |
| `AUTH_ENABLED` | Docker 镜像默认 `true`；本地未设置时为 `false`，可继续不登录进行页面开发 |
| `SSO_CLIENT_ID` | 默认沿用原 ZIP 的 `APM0015442`，可覆盖 |
| `USE_SECRET_MANAGER` | 默认 `1`，使用 Pod 的 Google 默认凭据读取同一 Secret；设为 `0` 时仅使用注入的 Client Secret |
| `GCP_PROJECT_ID`、`SECRET_ID`、`SECRET_VERSION` | 默认 `edp-pdev-restrict-paops`、`paops-streamlit-pdev`、`latest`，与原 ZIP 相同 |
| `SSO_CLIENT_SECRET` | 可选的环境变量回退值，也接受 `sso_client_secret`；正常从 Secret JSON 的 `sso_client_secret` 字段自动读取 |
| `REDIRECT_URI` | 默认 `https://pa-caddie-demo.pdev.cvshealth.com/token`，可覆盖；须与 Ping Client 登记的回调一致 |
| `SHARED_SECRET_KEY` | 可选；未设置时从读取的 Client Secret、Client ID、回调地址派生本应用的稳定会话密钥；不复用原 ZIP 的公开默认字符串 |
| `TOKEN_EXPIRATION_TIME` | 本地登录会话时长，默认 7200 秒，且不超过 Ping 返回的 expires_in |
| `AUTH_URL`、`TOKEN_ENDPOINT`、`USERINFO_ENDPOINT` | 默认使用 `authsvc-dev.cvshealth.com` 的 Dev SSO 地址；Prod 地址已在代码和 `.env.example` 中注释保留 |

完整默认 Secret 路径是 `projects/edp-pdev-restrict-paops/secrets/paops-streamlit-pdev/versions/latest`。`secret_loader.py` 与原项目一样通过 Google Application Default Credentials（GKE 中的 Pod 身份）调用 Secret Manager，解析 JSON 并读取 `sso_client_secret`，不输出真实密钥。密钥内容只在进程内使用，不写文件。多个副本使用相同 Secret 和回调地址会得到相同会话密钥；Secret 轮换后重启的副本会要求已有用户重新登录。镜像构建及默认本地开发不会访问 Secret Manager。

本实现使用 Basic Client Authentication、`openid profile email PHGroup` scope 和 PKCE S256。当前默认使用 Dev SSO，Client ID、Secret 路径及回调保持原配置，回调为 `https://pa-caddie-demo.pdev.cvshealth.com/token`。需确认该 Client 和 Secret 在 Dev 有效，且 Dev 允许此回调；userinfo 必须返回当前用户的 `email`（或 mail）、`sub` 和目标组。本地自动测试使用 Mock Secret Manager 和 Mock Ping，不读取公司密钥。若 Deployment 已设置上述三个端点环境变量，需要同步改为 Dev 或删除覆盖值，否则环境变量仍会覆盖代码默认值。

### 行为与日志

- 未登录打开 `/` 跳到 `/login`，再进入公司 Ping。已有公司登录会话时，是否需要再次输入凭据由 Ping 决定。
- `/token` 回调获取 userinfo：允许组成员设置 Secure/HttpOnly 会话 Cookie 并跳转页面；不匹配返回 **403**。
- Cookie 验证和组检查覆盖页面、静态文件、数据接口和 API 文档；未认证直接访问数据接口返回 **401**。
- `/health` 始终免登录返回 **200**。认证配置缺失时应用仍可启动并响应健康探针，其余入口返回 **503**，不会绕过权限检查放行。
- `/logout` 清除本应用会话；不退出整个公司登录会话。
- 日志输出 `access_check` JSON，包含时间、已验证邮箱、允许/拒绝、原因与命中组；不记录 Token、密码或完整组名单。Uvicorn 的 `/token` 请求日志去除查询参数，Ingress 日志需由平台设置。
- 测试期间默认增加 `userinfo_debug` 日志：在权限判断前记录 userinfo 的字段名，以及邮箱和群组相关字段的实际值（包括 groups_cn/groups/PHGroup/memberOf 等），不输出 Token 或密钥。即使随后返回 403 也可在 Pod 日志中查看。设置 `AUTH_LOG_USERINFO=false` 可关闭此临时诊断。
- 不将 access token/refresh token 放入浏览器会话；本地 Cookie 只保存邮箱、用户标识、命中组和有效期。登录 state 与 PKCE 信息放在独立的短期签名 Cookie 中。
- 会话期间不会逐请求查询目录，组成员变更在会话过期并重新登录后体现。若需要更快生效，可降低 TOKEN_EXPIRATION_TIME。

测试包含真实 HTTP 请求形态的 Mock Ping（Basic 认证、code 交换、userinfo、groups_cn/groups、403、state/PKCE、过期或伪造会话），不需要公司凭据。
