#!/bin/bash

# =============================================================================
# Iudex API - Dependency Installation Script
# =============================================================================
# This script installs all required Python packages and system dependencies
# for the Iudex API backend
#
# Usage: ./scripts/install_dependencies.sh
# =============================================================================

set -e  # Exit on error

echo "🚀 Installing Iudex API Dependencies..."
echo ""

# =============================================================================
# Check Prerequisites
# =============================================================================
echo "📋 Checking prerequisites..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✅ Python version: $PYTHON_VERSION"

# Check if Poetry is installed (optional but recommended)
if command -v poetry &> /dev/null; then
    echo "✅ Poetry is installed"
    USE_POETRY=true
else
    echo "⚠️  Poetry not found. Using pip instead."
    echo "   Install Poetry for better dependency management: https://python-poetry.org"
    USE_POETRY=false
fi

echo ""

# =============================================================================
# Install Python Dependencies
# =============================================================================
echo "📦 Installing Python packages..."

if [ "$USE_POETRY" = true ]; then
    poetry install
else
    # Core dependencies
    pip install --upgrade pip
    pip install fastapi[all] uvicorn[standard]
    pip install sqlalchemy[asyncio] aiosqlite asyncpg
    pip install pydantic pydantic-settings
    pip install python-jose[cryptography] passlib[bcrypt]
    pip install python-multipart
    pip install loguru
    
    # AI Providers
    pip install openai anthropic google-generativeai
    
    # Document Processing
    pip install pdfplumber python-docx pytesseract Pillow
    pip install odfpy  # ODT support
    
    # Text-to-Speech
    pip install gtts google-cloud-texttospeech boto3
    
    # Transcription
    pip install openai-whisper
    # or just: pip install openai (for API-based transcription)
    
    # Web Scraping (if needed)
    pip install aiohttp beautifulsoup4
fi

echo "✅ Python packages installed"
echo ""

# =============================================================================
# Install System Dependencies (macOS)
# =============================================================================
echo "🔧 Installing system dependencies..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "Detected macOS"
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew is not installed. Please install it first:"
        echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    
    echo "Installing Tesseract OCR..."
    brew list tesseract &>/dev/null || brew install tesseract
    
    echo "Installing Tesseract Portuguese language data..."
    brew list tesseract-lang &>/dev/null || brew install tesseract-lang
    
    echo "Installing FFmpeg (for audio/video processing)..."
    brew list ffmpeg &>/dev/null || brew install ffmpeg
    
    echo ""
    echo "📊 Installing diagram generation tools (optional)..."
    echo "These are optional but recommended for diagram generation:"
    echo ""
    
    read -p "Install Graphviz? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        brew list graphviz &>/dev/null || brew install graphviz
    fi
    
    read -p "Install PlantUML? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        brew list plantuml &>/dev/null || brew install plantuml
    fi
    
    read -p "Install Mermaid CLI? (requires Node.js) (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v npm &> /dev/null; then
            npm install -g @mermaid-js/mermaid-cli
        else
            echo "⚠️  npm not found. Please install Node.js first."
        fi
    fi
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    echo "Detected Linux"
    
    # Try to detect package manager
    if command -v apt-get &> /dev/null; then
        echo "Using apt-get..."
        sudo apt-get update
        sudo apt-get install -y tesseract-ocr tesseract-ocr-por
        sudo apt-get install -y ffmpeg
        sudo apt-get install -y graphviz plantuml  # Optional
    elif command -v yum &> /dev/null; then
        echo "Using yum..."
        sudo yum install -y tesseract tesseract-langpack-por
        sudo yum install -y ffmpeg
        sudo yum install -y graphviz plantuml  # Optional
    else
        echo "⚠️  Could not detect package manager. Please install manually:"
        echo "   - Tesseract OCR"
        echo "   - FFmpeg"
        echo "   - Graphviz (optional)"
        echo "   - PlantUML (optional)"
    fi
else
    echo "⚠️  Unsupported OS: $OSTYPE"
    echo "Please install the following manually:"
    echo "   - Tesseract OCR (with Portuguese language data)"
    echo "   - FFmpeg"
    echo "   - Graphviz (optional)"
    echo "   - PlantUML (optional)"
fi

echo ""
echo "✅ System dependencies installed"
echo ""

# =============================================================================
# Setup Storage Directories
# =============================================================================
echo "📁 Creating storage directories..."

mkdir -p storage/uploads
mkdir -p storage/podcasts
mkdir -p storage/diagrams
mkdir -p storage/temp

echo "✅ Storage directories created"
echo ""

# =============================================================================
# Verify Installation
# =============================================================================
echo "🔍 Verifying installation..."
echo ""

# Check Tesseract
if command -v tesseract &> /dev/null; then
    TESSERACT_VERSION=$(tesseract --version | head -n 1)
    echo "✅ Tesseract: $TESSERACT_VERSION"
else
    echo "❌ Tesseract not found"
fi

# Check FFmpeg
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n 1 | awk '{print $1, $2, $3}')
    echo "✅ FFmpeg: $FFMPEG_VERSION"
else
    echo "⚠️  FFmpeg not found (required for audio/video transcription)"
fi

# Check optional tools
if command -v dot &> /dev/null; then
    echo "✅ Graphviz installed"
else
    echo "ℹ️  Graphviz not installed (optional)"
fi

if command -v plantuml &> /dev/null; then
    echo "✅ PlantUML installed"
else
    echo "ℹ️  PlantUML not installed (optional)"
fi

if command -v mmdc &> /dev/null; then
    echo "✅ Mermaid CLI installed"
else
    echo "ℹ️  Mermaid CLI not installed (optional)"
fi

echo ""
echo "============================================="
echo "✅ Installation Complete!"
echo "============================================="
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and configure your API keys"
echo "2. Run the application: uvicorn app.main:app --reload"
echo ""
echo "For production setup, see the deployment documentation."
echo ""
