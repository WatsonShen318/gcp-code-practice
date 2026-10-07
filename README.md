# Cloud Run Hello World

一个零依赖的 Python HTTP 服务，可直接部署到 Google Cloud Run。

## 接口

- `GET /` → `{"message": "Hello World from Cloud Run!"}`
- `GET /healthz` → `{"status": "ok"}`

## 本地运行

```bash
python app.py
```

访问 <http://localhost:8080>。

运行测试：

```bash
python -m unittest -v
```

## 修改并部署到 Cloud Run

先安装并登录 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)：

```powershell
gcloud auth login
```

修改 `app.py` 后，提交代码并在仓库根目录运行：

```powershell
git add .
git commit -m "Update greeting"
git push
./deploy.ps1
```

`deploy.ps1` 会把当前仓库内容上传到项目 `triple-brook-472818-u8`，构建容器，并更新
`us-central1` 中的 `hello-world` 服务。每次部署会创建一个新的 Cloud Run revision，
服务 URL 保持不变：

<https://hello-world-489762766956.us-central1.run.app>

例如，把 `app.py` 中的 `Hello World from Cloud Run!` 改成 `Hello WS`，提交并重新运行
`./deploy.ps1` 后，网页就会显示新的内容。

> `git commit` 和 `git push` 用来保存代码历史；真正触发 Cloud Run 更新的是
> `./deploy.ps1`。如果希望 `git push` 后自动部署，可以进一步配置 GitHub Actions。
