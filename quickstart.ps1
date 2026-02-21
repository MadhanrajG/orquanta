# AI GPU Cloud - Quick Start Script
# This script helps you get the platform running quickly

Write-Host "🚀 AI GPU Cloud - Quick Start" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}

# Check Docker
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker not found. Please install Docker Desktop" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Prerequisites check complete!" -ForegroundColor Green
Write-Host ""

# Ask user what they want to do
Write-Host "What would you like to do?" -ForegroundColor Cyan
Write-Host "1. Install dependencies only"
Write-Host "2. Run with Docker Compose (recommended for testing)"
Write-Host "3. Run API directly (for development)"
Write-Host "4. View documentation"
Write-Host ""

$choice = Read-Host "Enter your choice (1-4)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
        
        # Create virtual environment
        if (-not (Test-Path "venv")) {
            Write-Host "Creating virtual environment..." -ForegroundColor Yellow
            python -m venv venv
        }
        
        # Activate virtual environment
        Write-Host "Activating virtual environment..." -ForegroundColor Yellow
        & .\venv\Scripts\Activate.ps1
        
        # Install dependencies
        Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Yellow
        pip install -r requirements.txt
        
        Write-Host ""
        Write-Host "✓ Dependencies installed successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "To activate the virtual environment, run:" -ForegroundColor Cyan
        Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
    }
    
    "2" {
        Write-Host ""
        Write-Host "Starting services with Docker Compose..." -ForegroundColor Yellow
        Write-Host ""
        
        # Check if docker-compose is available
        try {
            docker-compose --version | Out-Null
            $composeCmd = "docker-compose"
        } catch {
            $composeCmd = "docker compose"
        }
        
        # Start services
        Write-Host "Building and starting all services..." -ForegroundColor Yellow
        & $composeCmd up -d --build
        
        Write-Host ""
        Write-Host "✓ Services started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access the platform at:" -ForegroundColor Cyan
        Write-Host "  API:        http://localhost:8000" -ForegroundColor White
        Write-Host "  API Docs:   http://localhost:8000/docs" -ForegroundColor White
        Write-Host "  Grafana:    http://localhost:3000 (admin/admin)" -ForegroundColor White
        Write-Host "  Prometheus: http://localhost:9090" -ForegroundColor White
        Write-Host ""
        Write-Host "To view logs, run:" -ForegroundColor Cyan
        Write-Host "  $composeCmd logs -f api" -ForegroundColor White
        Write-Host ""
        Write-Host "To stop services, run:" -ForegroundColor Cyan
        Write-Host "  $composeCmd down" -ForegroundColor White
    }
    
    "3" {
        Write-Host ""
        Write-Host "Running API directly..." -ForegroundColor Yellow
        Write-Host ""
        
        # Activate virtual environment if it exists
        if (Test-Path "venv\Scripts\Activate.ps1") {
            Write-Host "Activating virtual environment..." -ForegroundColor Yellow
            & .\venv\Scripts\Activate.ps1
        }
        
        # Check if dependencies are installed
        Write-Host "Checking dependencies..." -ForegroundColor Yellow
        try {
            python -c "import fastapi" 2>&1 | Out-Null
        } catch {
            Write-Host "Dependencies not installed. Installing now..." -ForegroundColor Yellow
            pip install -r requirements.txt
        }
        
        Write-Host ""
        Write-Host "Starting API server..." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Note: This runs without database and other services." -ForegroundColor Yellow
        Write-Host "For full functionality, use Docker Compose (option 2)." -ForegroundColor Yellow
        Write-Host ""
        
        # Run the API
        python main.py
    }
    
    "4" {
        Write-Host ""
        Write-Host "📚 Documentation Files:" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  README.md                   - Quick start and overview"
        Write-Host "  ARCHITECTURE.md             - Detailed system architecture"
        Write-Host "  LAUNCH_READINESS.md         - Competitive audit & launch plan"
        Write-Host "  DEPLOYMENT.md               - Production deployment guide"
        Write-Host "  IMPLEMENTATION_SUMMARY.md   - What we built and why"
        Write-Host "  PROJECT_STRUCTURE.md        - Project organization"
        Write-Host ""
        Write-Host "Opening README.md..." -ForegroundColor Yellow
        Start-Process "README.md"
    }
    
    default {
        Write-Host "Invalid choice. Please run the script again." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Need help? Check out:" -ForegroundColor Cyan
Write-Host "  • README.md for quick start"
Write-Host "  • ARCHITECTURE.md for technical details"
Write-Host "  • DEPLOYMENT.md for production setup"
Write-Host ""
Write-Host "Happy coding! 🚀" -ForegroundColor Green
