param(
    [string]$ProjectId = "triple-brook-472818-u8",
    [string]$Region = "us-central1",
    [string]$Service = "hello-world"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "找不到 gcloud。请先安装 Google Cloud CLI 并运行 gcloud auth login。"
}

gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    --project $ProjectId

if ($LASTEXITCODE -ne 0) {
    throw "启用 Google Cloud API 失败。"
}

gcloud run deploy $Service `
    --source $PSScriptRoot `
    --project $ProjectId `
    --region $Region `
    --allow-unauthenticated `
    --quiet

if ($LASTEXITCODE -ne 0) {
    throw "Cloud Run 部署失败。"
}

Write-Host "部署完成：运行 'gcloud run services describe $Service --project $ProjectId --region $Region --format=value(status.url)' 查看网址。"
