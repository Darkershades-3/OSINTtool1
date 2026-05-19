import asyncio
import aiohttp
import random
import json
import os
import logging
import urllib.request

# Configure structural terminal logging outputs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0"
]

class StealthSession:
    def __init__(self, proxy_file="proxies.json"):
        self.proxy_file = proxy_file
        self.proxies = self._load_proxies()
        
    def _load_proxies(self):
        """Harvests fresh, checked public proxies directly from high-speed open-source repository mirrors."""
        # High-availability raw text endpoint updated hourly by the security community
        raw_proxy_url = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        
        try:
            logging.info("[*] Pinging high-speed community repositories for active HTTP nodes...")
            req = urllib.request.Request(raw_proxy_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=6) as response:
                raw_text = response.read().decode('utf-8')
                all_proxies = [line.strip() for line in raw_text.splitlines() if line.strip()]
                
                if all_proxies:
                    # Sample 15 random nodes to keep our rotational operational pool compact and fast
                    fresh_pool = random.sample(all_proxies, min(15, len(all_proxies)))
                    logging.info(f"[+] Successfully intercepted {len(fresh_pool)} fresh community proxy nodes!")
                    
                    # Persist down to local cache file
                    with open(self.proxy_file, 'w') as f:
                        json.dump(fresh_pool, f)
                    return fresh_pool
        except Exception as api_err:
            logging.warning(f"[-] Community harvest mirror unreachable ({api_err}). Dropping back to local storage matrix.")

        # --- Local fallback block if network harvesting fails ---
        if not os.path.exists(self.proxy_file):
            logging.warning(f"'{self.proxy_file}' missing! Stealth components will fallback to Direct Connections.")
            return []
            
        try:
            with open(self.proxy_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    logging.info(f"[+] Loaded {len(data)} cached proxy configurations from local storage.")
                    return data
                return []
        except Exception as e:
            logging.error(f"[-] Encountered error parsing local proxies.json: {e}")
            return []

    def _get_evasive_headers(self):
        """Generates spoofed connection parameters to simulate a real web browser profile."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    def _get_random_proxy_scheme(self):
        """Extracts a node from our list and structures it as an HTTP scheme string."""
        if not self.proxies:
            return None
        selected = random.choice(self.proxies)
        return f"http://{selected}"

    async def fetch(self, url, max_retries=3):
        """Executes an asynchronous network request wrapped in dynamic rotation and safety layers."""
        for attempt in range(max_retries):
            proxy = self._get_random_proxy_scheme()
            headers = self._get_evasive_headers()
            
            # Use a tight 10-second timeout to prevent dead nodes from stalling tool execution
            timeout = aiohttp.ClientTimeout(total=10)
            
            try:
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                    logging.info(f"[*] Dispatching fetch request -> Proxy Target: {proxy or 'Direct Routing'}")
                    
                    async with session.get(url, proxy=proxy) as response:
                        if response.status == 200:
                            return await response.text()
                        else:
                            logging.warning(f"[-] Target endpoint rejected request via {proxy or 'Direct'} with Status: {response.status}")
            except Exception as e:
                logging.warning(f"[-] Connection Fault via proxy target {proxy or 'Direct'} on Attempt {attempt + 1}: {str(e)[:60]}")
                
                # Yield execution briefly before running the next random proxy try
                await asyncio.sleep(1)
                
        # Final emergency processing layer: Attempt direct transmission if everything fails
        logging.info("[*] Executing final safety processing fallback via clear direct interface...")
        try:
            async with aiohttp.ClientSession(headers=self._get_evasive_headers(), timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
        except Exception as fallback_error:
            logging.critical(f"[-] Complete Network Pipeline Failure to target endpoint: {fallback_error}")
        return None

# --- Verification Entry Point ---
async def verify_engine():
    engine = StealthSession()
    target = "https://httpbin.org/anything"
    
    print("\n================ TESTING STEALTH INTERFACE ================")
    response_payload = await engine.fetch(target)
    if response_payload:
        print("\n[+] Validation Complete. Output Payload Verified:")
        print(response_payload[:600])
    print("===========================================================\n")

if __name__ == "__main__":
    asyncio.run(verify_engine())
