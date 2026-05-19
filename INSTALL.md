Installation and Execution Guide

​This guide provides a structured walkthrough to get the Intel Portal framework operational from a blank terminal.
​
🛠️ Phase 1: Environment Preparation
​Ensure your environment is ready to handle network requests and metadata processing.
​
1.1 Install System Dependencies
​
For Termux (Android):
pkg update && pkg upgrade -y
pkg install python python-pip clang libjpeg-turbo git -y

For Ubuntu / Debian / Linux:
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv build-essential libjpeg-dev zlib1g-dev git -y

1.2 Install uv (The Engine)
​We use uv for high-performance dependency resolution.
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

 Phase 2: Deployment
​
2.1 Clone/Setup Workspace
mkdir -p intel_portal_workspace
cd intel_portal_workspace
mkdir -p scanned_images

2.2 Configure API Access
​
The AI synthesis component requires an API key. Export it so the script can access it securely.
​
For this session only:
export OPENROUTER_API_KEY="sk-or-v1-your-token-here"

To make it permanent:
echo 'export OPENROUTER_API_KEY="sk-or-v1-your-token-here"' >> ~/.bashrc
source ~/.bashrc

Phase 3: Execution & Troubleshooting
​
3.1 Run via Ephemeral Injection
​
This command fetches dependencies and runs the portal without cluttering your global environment:
uv run --with aiohttp --with pillow intel_portal.py

Suggestions for Power Users

Automate Image Processing: Create a cron job to move photos from your camera directory into ./scanned_images/ so the portal processes them automatically.

Refine Target Lists: Edit the USERNAME_TRACKER_SITES dictionary in intel_portal.py to add platforms relevant to your research.

Use Virtual Environments: If you extend the code significantly, initialize a virtual environment:
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

