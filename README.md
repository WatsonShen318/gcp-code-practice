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

## 部署到 Cloud Run

先安装并登录 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)：

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

从仓库根目录部署源码：

```bash
gcloud run deploy hello-world \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

部署完成后，命令会输出公开访问地址。
