import asyncio
import aiohttp
import os
import sys
import json
import re
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging

# Import your custom stealth rotation engine
from stealth import StealthSession

# --- Configuration ---
IMAGE_SCAN_FOLDER = './scanned_images'

# Dictionary of target sites for username tracking
USERNAME_TRACKER_SITES = {
    'github': {
        'url_template': 'https://github.com/{username}',
        'not_found_indicator': {'text_contains': '"pinned-items-not-found"'}
    },
    'reddit': {
        'url_template': 'https://www.reddit.com/user/{username}',
        'not_found_indicator': {'text_contains': 'Page not found'}
    },
    'instagram': {
        'url_template': 'https://www.instagram.com/{username}',
        'not_found_indicator': {'text_contains': "Sorry, this page isn't available."}
    }
}

# AI Model Configuration
AI_MODEL_FAST = "openrouter/auto"

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize the stealth engine globally once
stealth_engine = StealthSession()

# --- Component A: Image EXIF Analyzer ---

def get_exif_data(image_path):
    exif_data = {}
    try:
        with Image.open(image_path) as img:
            if 'exif' in img.info:
                for tag_id, value in img.getexif().items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'GPSInfo':
                        gps_info = {}
                        for gps_tag_id, gps_value in value.items():
                            gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_info[gps_tag] = gps_value
                        exif_data[tag] = gps_info
                    else:
                        exif_data[tag] = value
    except FileNotFoundError:
        logging.error(f"Image file not found: {image_path}")
    except Exception as e:
        logging.error(f"Error processing EXIF data for {image_path}: {e}")
    return exif_data

def format_exif_data(exif_data, image_path):
    formatted_info = {
        "file_path": image_path,
        "timestamps": {},
        "camera_info": {},
        "gps_coordinates": None,
        "software": None
    }

    for tag, value in exif_data.items():
        if tag in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
            try:
                formatted_info["timestamps"][tag] = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').isoformat()
            except ValueError:
                formatted_info["timestamps"][tag] = str(value)
        elif tag in ('Model', 'Make'):
            formatted_info["camera_info"][tag] = str(value)
        elif tag == 'Software':
            formatted_info["software"] = str(value)
        elif tag == 'GPSInfo':
            if 'GPSLatitude' in value and 'GPSLongitude' in value:
                lat_deg = value['GPSLatitude']
                lat_ref = value['GPSLatitudeRef']
                lon_deg = value['GPSLongitude']
                lon_ref = value['GPSLongitudeRef']

                def dms_to_decimal(dms, ref):
                    degrees = dms[0]
                    minutes = dms[1]
                    seconds = dms[2]
                    decimal_degrees = degrees + (minutes / 60.0) + (seconds / 3600.0)
                    if ref in ['S', 'W']:
                        decimal_degrees = -decimal_degrees
                    return decimal_degrees

                try:
                    formatted_info["gps_coordinates"] = {
                        "latitude": dms_to_decimal(lat_deg, lat_ref),
                        "longitude": dms_to_decimal(lon_deg, lon_ref)
                    }
                except Exception as e:
                    logging.warning(f"Could not convert GPS coordinates for {image_path}: {e}")

    if not formatted_info["timestamps"] and "DateTime" in exif_data:
         try:
            formatted_info["timestamps"]["DateTime"] = datetime.strptime(str(exif_data["DateTime"]), '%Y:%m:%d %H:%M:%S').isoformat()
         except ValueError:
            formatted_info["timestamps"]["DateTime"] = str(exif_data["DateTime"])

    formatted_info = {k: v for k, v in formatted_info.items() if v}
    if "timestamps" in formatted_info and not formatted_info["timestamps"]:
        del formatted_info["timestamps"]
    if "camera_info" in formatted_info and not formatted_info["camera_info"]:
        del formatted_info["camera_info"]

    return formatted_info

async def scan_images_for_exif(folder_path):
    image_metadata_list = []
    if not os.path.isdir(folder_path):
        logging.warning(f"Image scan folder not found: {folder_path}")
        return image_metadata_list

    logging.info(f"Scanning for images in: {folder_path}")
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            image_path = os.path.join(folder_path, filename)
            logging.debug(f"Processing image: {image_path}")
            exif_data = get_exif_data(image_path)
            if exif_data:
                formatted_data = format_exif_data(exif_data, image_path)
                if formatted_data:
                    image_metadata_list.append(formatted_data)
    logging.info(f"Finished scanning images. Found EXIF data for {len(image_metadata_list)} images.")
    return image_metadata_list

# --- Component B: Asynchronous Username Tracker & Deep Scraper ---

def extract_profile_intelligence(site_name, html_content):
    """Parses verified profile HTML to extract bios, locations, and external links."""
    intel = {"bio": None, "extracted_links": [], "location": None}
    if not html_content:
        return intel

    if site_name == 'github':
        bio_match = re.search(r'data-bio-text="([^"]+)"', html_content)
        if bio_match:
            intel["bio"] = bio_match.group(1)
            
        loc_match = re.search(r'itemprop="homeLocation"[^>]*>\s*<span[^>]*>([^<]+)</span>', html_content)
        if loc_match:
            intel["location"] = loc_match.group(1).strip()

    found_links = re.findall(r'href="(https?://(?:www\.)?(?:twitter\.com|x\.com|linkedin\.com|instagram\.com|[^"\s>]+))"', html_content)
    if found_links:
        intel["extracted_links"] = list(set([lnk for lnk in found_links if site_name not in lnk]))[:5]

    return intel

async def check_username_on_site(username, site_name, site_config):
    url_template = site_config['url_template']
    url = url_template.format(username=username)
    not_found_indicator = site_config.get('not_found_indicator', {})

    try:
        content = await stealth_engine.fetch(url)
        
        if content is None:
            logging.debug(f"[-] Target interface returned no payload response for target: {url}")
            return None

        if 'text_contains' in not_found_indicator:
            if not_found_indicator['text_contains'] in content:
                logging.debug(f"[-] Username '{username}' not detected on platform profile: {url}")
                return None

        logging.debug(f"[+] Footprint verified for username '{username}' on: {url}")
        
        # Profile confirmed! Scrape deeper intelligence data points
        profile_intel = extract_profile_intelligence(site_name, content)
        
        return {
            "platform": site_name,
            "url": url,
            "metadata": profile_intel
        }

    except Exception as e:
        logging.error(f"[-] Exception encountered checking {url}: {e}")
        return None

async def track_username(username):
    logging.info(f"Tracking username: '{username}'")
    active_footprint = []
    
    tasks = []
    for site_name, config in USERNAME_TRACKER_SITES.items():
        tasks.append(check_username_on_site(username, site_name, config))

    results = await asyncio.gather(*tasks)

    for item in results:
        if item:
            active_footprint.append(item)

    logging.info(f"Username '{username}' footprint verified on {len(active_footprint)} platforms.")
    return active_footprint

# --- Component C: Smart AI Synthesis Layer (OpenRouter) ---

async def synthesize_findings_with_ai(image_data, username_footprint):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("\n" + "="*60)
        print("  Error: OPENROUTER_API_KEY environment variable not detected.")
        print("  Skipping AI analysis phase.")
        print("="*60 + "\n")
        return {"error": "API key not found"}

    logging.info("Synthesizing findings with AI...")

    prompt_parts = ["Analyze the following intelligence data:\n\n"]

    if image_data:
        prompt_parts.append("--- Image EXIF Data ---\n")
        for item in image_data:
            prompt_parts.append(json.dumps(item, indent=2))
            prompt_parts.append("\n")
    else:
        prompt_parts.append("--- No Image EXIF Data Found ---\n\n")

    if username_footprint:
        prompt_parts.append("--- Username Footprint & Scraped Metadata ---\n")
        for item in username_footprint:
            prompt_parts.append(json.dumps(item, indent=2))
            prompt_parts.append("\n")
    else:
        prompt_parts.append("--- No Username Footprint Found ---\n\n")

    prompt_parts.append("\nProvide a concise intelligence summary, highlighting potential connections or points of interest.")
    full_prompt = "".join(prompt_parts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": AI_MODEL_FAST,
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 500,
        "temperature": 0.3
    }
    openrouter_api_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(openrouter_api_url, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_summary = result.get('choices', [{}])[0].get('message', {}).get('content', 'AI analysis failed to produce content.')
                    logging.info("AI synthesis complete.")
                    return {"ai_summary": ai_summary}
                else:
                    error_details = await response.text()
                    logging.error(f"OpenRouter API error: {response.status} - {error_details}")
                    return {"error": f"AI analysis failed: {response.status}"}
    except Exception as e:
        logging.error(f"Unexpected error during AI synthesis execution: {e}")
        return {"error": "AI pipeline synchronization failure."}

# --- Main Orchestration ---

async def main():
    print("Starting Intel Portal...")

    # Component A: Image Scan
    print(f"\n[+] Starting Image EXIF Analysis in '{IMAGE_SCAN_FOLDER}'...")
    if not os.path.exists(IMAGE_SCAN_FOLDER):
        os.makedirs(IMAGE_SCAN_FOLDER)
        print(f"Created directory: {IMAGE_SCAN_FOLDER}")
    image_data = await scan_images_for_exif(IMAGE_SCAN_FOLDER)
    print(f"[+] Image EXIF Analysis Complete. Found data for {len(image_data)} images.")

    # Component B: Username Track & Scrape
    username_to_track = input("\nEnter username handle to track: ").strip()
    if not username_to_track:
        print("No username entered. Skipping username tracking.")
        username_footprint = []
    else:
        print(f"\n[+] Starting Username Tracking & Deep Scraping for '{username_to_track}'...")
        username_footprint = await track_username(username_to_track)
        print(f"[+] Tracking Complete. Gathered intel on {len(username_footprint)} profiles.")

    # Component C: AI Synthesis
    print("\n[+] Initiating AI Synthesis Layer...")
    ai_results = await synthesize_findings_with_ai(image_data, username_footprint)

    # Output Report
    print("\n" + "="*60)
    print("          INTELLIGENCE REPORT SUMMARY")
    print("="*60)

    if image_data:
        print("\n--- Image EXIF Data Found ---")
        for item in image_data:
            print(json.dumps(item, indent=2))
    else:
        print("\n--- No Image EXIF Data Found ---")

    if username_footprint:
        print("\n--- Verified Username Footprint ---")
        for item in username_footprint:
            print(f"- {item['platform'].upper()}: {item['url']}")
            if item['metadata']['bio']:
                print(f"  > Bio: {item['metadata']['bio']}")
            if item['metadata']['location']:
                print(f"  > Loc: {item['metadata']['location']}")
            if item['metadata']['extracted_links']:
                print(f"  > Ext Links: {', '.join(item['metadata']['extracted_links'])}")
    else:
        print("\n--- No Username Footprint Found ---")

    if "error" in ai_results:
        print(f"\n--- AI Analysis Status ---\n{ai_results['error']}")
    elif ai_results.get("ai_summary"):
        print("\n--- AI Synthesis Summary ---\n" + ai_results["ai_summary"])

    print("\n" + "="*60)
    print("Report generation complete.")

    save_raw_data = input("Save raw findings to a file? (y/N): ").strip().lower()
    if save_raw_data == 'y':
        output_filename = f"intel_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_data = {
            "image_data": image_data,
            "username_footprint": username_footprint,
            "ai_results": ai_results
        }
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=4, ensure_ascii=False)
            print(f"Raw data saved to: {output_filename}")
        except Exception as e:
            logging.error(f"Failed to save report: {e}")

if __name__ == "__main__":
    if not os.path.exists(IMAGE_SCAN_FOLDER):
        os.makedirs(IMAGE_SCAN_FOLDER)
    asyncio.run(main())
