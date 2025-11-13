param(
    [string]$Message = "auto migration",
    [switch]$ForceInit
)

# PowerShell helper to run Flask-Migrate commands on Windows.
# Usage: .\run_migrations.ps1 -Message "describe changes"

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

if (-not (Test-Path venv\Scripts\Activate)) {
    Write-Host "Warning: virtualenv activate script not found at venv\Scripts\Activate. Make sure your venv is present and activated." -ForegroundColor Yellow
} else {
    Write-Host "Activating virtualenv..."
    & venv\Scripts\Activate
}

# Ensure FLASK_APP is set
$env:FLASK_APP = 'app.py'
Write-Host "FLASK_APP set to $env:FLASK_APP"

# Initialize migrations folder if missing or forced
if (-not (Test-Path migrations) -or $ForceInit) {
    Write-Host "Initializing migrations (flask db init)..."
    flask db init
} else {
    Write-Host "migrations/ exists — skipping init"
}

# Run migrate (autogenerate). The user should inspect the generated file.
Write-Host "Generating migration (flask db migrate) with message: $Message"
flask db migrate -m "$Message"

# Apply the migration
Write-Host "Applying migration (flask db upgrade)"
flask db upgrade

Write-Host "Done. Please review migrations/versions for the generated migration script before committing." -ForegroundColor Green
