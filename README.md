# Intel Portal 🕵️‍♂️

An advanced, asynchronous Open-Source Intelligence (OSINT) framework designed for rapid footprinting, metadata extraction, and AI-driven threat synthesis.

## 🚀 Core Capabilities

* **Deep Username Tracking & Scraping:** Asynchronously verifies target handles across multiple platforms (GitHub, Reddit, Instagram). Bypasses simple validation by scraping deep intelligence markers such as user biographies, geographical locations, and external pivot links (Twitter, LinkedIn, etc.).
* **Stealth Routing Engine:** All network requests are routed through a custom `StealthSession` module. This engine automatically harvests live community proxies, rotates IP addresses on failure, and spoofs modern browser headers to bypass rate limits and anti-bot defenses.
* **Image EXIF Forensics:** Iteratively scans local directories (`./scanned_images`) to extract hidden metadata from target assets, including capture timestamps, device/camera models, and exact GPS coordinates (converted to decimal format).
* **AI Intelligence Synthesis:** Integrates with the OpenRouter API to feed all extracted data (EXIF + Scraped Footprints) into an LLM, generating a cohesive, highly contextual threat intelligence summary.

---

## 🔄 Dynamic Proxy Lifecycle & Update Mechanics

The `StealthSession` architecture operates on a **demand-driven, stateless harvesting cycle** to ensure network resilience without manual upkeep.

### 1. How the Proxies Update
* **Upstream Interception:** Every time the application initializes `StealthSession()`, the framework dispatches an asynchronous background request to high-speed community repositories and edge CDNs caching active HTTP nodes.
* **On-the-Fly Scraping:** It intercepts a fresh block of **15 dynamic proxy nodes** directly into an in-memory stack. 
* **Rotation Loop:** When checking a target handle, the engine pops a proxy off the stack. If that node drops, hits a connection reset, or encounters a timeout, the engine discards it, shifts to the next available proxy in the pool, and retries the target instantly.

### 2. How the System "Knows" to Fetch or Fallback
The engine dynamically evaluates the health of the network layer using three automated validation guardrails:

* **The Cache Counter:** The script actively monitors the size of its current proxy array. If the pool drops to zero, it automatically knows its current routing layer is exhausted.
* **Explicit Exception Tracking:** The runtime catches system-level socket errors. If a node drops traffic (e.g., triggering a `[Errno 104] Connection reset by peer` or a connection timeout), the system immediately logs the failure and flags the node as dead.
* **The Final Failover Threshold (Attempt 3):** The engine allows a maximum of 3 proxy rotation attempts per lookup. If it burns through 3 separate nodes on a single URL without success, it assumes the target platform's firewall is aggressively blocking public proxy pools. To ensure the intelligence cycle isn't broken, it intelligently fires its **final safety fallback**—dropping the proxy layer entirely and spawning a pristine direct interface to complete the execution safely.

---

## 📂 Project Structure

* `intel_portal.py`: The main orchestrator. Handles asynchronous execution, data ingestion, and final report generation.
* `stealth.py`: The dynamic network evasion module. Manages proxy harvesting, connection fallbacks, and request headers.
* `./scanned_images/`: The designated drop-folder for static image assets to be parsed for EXIF data.

## 🛠️ Prerequisites

* Python 3.12+ 
* `uv` package manager (recommended for fast execution)
* An active OpenRouter API key for the synthesis layer

**Environment Setup:**
Ensure your OpenRouter API key is exported in your terminal environment before running the tool:
```bash
export OPENROUTER_API_KEY="your-api-key-here"

 Disclaimer
​This tool is built for educational purposes, digital forensics, and authorized red teaming/penetration testing only. Users are responsible for ensuring their actions comply with the Terms of Service of the target platforms.
