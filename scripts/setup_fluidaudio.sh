#!/bin/bash
# Setup script for FluidAudio - local speaker diarisation using CoreML
# This builds the FluidAudio CLI tool which runs on Apple Neural Engine

set -e

FLUIDAUDIO_SRC="${HOME}/.local/src/FluidAudio"
FLUIDAUDIO_BIN="${HOME}/.local/bin/fluidaudio"
FLUIDAUDIO_LIB="${HOME}/.local/lib"

echo "=== FluidAudio Setup ==="
echo ""

# Check if already installed
if [ -f "$FLUIDAUDIO_BIN" ]; then
    echo "FluidAudio is already installed at: $FLUIDAUDIO_BIN"
    "$FLUIDAUDIO_BIN" process --help 2>/dev/null | head -5 || echo "(installed)"
    echo ""
    read -p "Reinstall? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing installation."
        exit 0
    fi
fi

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v swift &> /dev/null; then
    echo "Error: Swift is not installed. Please install Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo "Error: git is not installed."
    exit 1
fi

# Ensure directories exist
mkdir -p "${HOME}/.local/bin"
mkdir -p "${HOME}/.local/src"
mkdir -p "${HOME}/.local/lib"

# Clone or update FluidAudio
if [ -d "$FLUIDAUDIO_SRC" ]; then
    echo "Updating existing FluidAudio source..."
    cd "$FLUIDAUDIO_SRC"
    git pull
else
    echo "Cloning FluidAudio..."
    git clone https://github.com/FluidInference/FluidAudio.git "$FLUIDAUDIO_SRC"
    cd "$FLUIDAUDIO_SRC"
fi

# Build in release mode with Swift 5 language mode (avoids Swift 6 strict concurrency errors)
echo ""
echo "Building FluidAudio (this may take a few minutes)..."
swift build -c release -Xswiftc -swift-version -Xswiftc 5

# Copy binary to PATH
echo ""
echo "Installing binary..."
cp ".build/release/fluidaudiocli" "$FLUIDAUDIO_BIN"
chmod +x "$FLUIDAUDIO_BIN"

# Copy ESpeakNG framework (required for TTS module)
echo "Installing ESpeakNG framework..."
if [ -d "${FLUIDAUDIO_SRC}/Frameworks/ESpeakNG.xcframework/macos-arm64_x86_64/ESpeakNG.framework" ]; then
    cp -R "${FLUIDAUDIO_SRC}/Frameworks/ESpeakNG.xcframework/macos-arm64_x86_64/ESpeakNG.framework" "$FLUIDAUDIO_LIB/"
fi

# Add rpath so binary can find the framework
install_name_tool -add_rpath "$FLUIDAUDIO_LIB" "$FLUIDAUDIO_BIN" 2>/dev/null || true

# Verify installation
echo ""
echo "=== Installation Complete ==="
echo "FluidAudio installed at: $FLUIDAUDIO_BIN"
echo ""
echo "First run will download diarisation models (~10MB)."
echo ""
echo "Usage:"
echo "  fluidaudio process <audio_file> --output results.json --threshold 0.7"
echo ""
echo "Output format (JSON):"
echo '  {"segments": [{"speakerId": "Speaker 1", "startTimeSeconds": 0.0, "endTimeSeconds": 45.2}]}'
