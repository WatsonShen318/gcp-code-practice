param(
    [string]$ProjectId = "triple-brook-472818-u8",
    [string]$Region = "us-central1",
    [string]$Service = "hello-world"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was not found. Install Google Cloud CLI and run: gcloud auth login"
}

gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    --project $ProjectId

if ($LASTEXITCODE -ne 0) {
    throw "Failed to enable the required Google Cloud APIs."
}

gcloud run deploy $Service `
    --source $PSScriptRoot `
    --project $ProjectId `
    --region $Region `
    --allow-unauthenticated `
    --quiet

if ($LASTEXITCODE -ne 0) {
    throw "Cloud Run deployment failed."
}

Write-Host "Deployment complete."
Write-Host "Service URL:"
gcloud run services describe $Service `
    --project $ProjectId `
    --region $Region `
    --format="value(status.url)"
