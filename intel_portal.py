import asyncio
import aiohttp
import os
import sys
import json
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import logging

# --- Configuration ---
IMAGE_SCAN_FOLDER = './scanned_images'  # Folder to scan for images
# Dictionary of target sites for username tracking
# Format: { 'site_name': {'url_template': '...', 'not_found_indicator': '...' or 'status_code': ...} }
USERNAME_TRACKER_SITES = {
    'github': {
        'url_template': 'https://github.com/{username}',
        'not_found_indicator': {'status_code': 404}
    },
    'reddit': {
        'url_template': 'https://www.reddit.com/user/{username}',
        'not_found_indicator': {'text_contains': 'Page not found'} # This might need adjustment based on Reddit's actual page content
    },
    'instagram': {
        'url_template': 'https://www.instagram.com/{username}',
        'not_found_indicator': {'text_contains': 'Sorry, this page isn\'t available.'} # This might need adjustment
    },
    'example_forum': {
        'url_template': 'https://www.exampleforum.com/member/{username}',
        'not_found_indicator': {'status_code': 404} # Assuming a 404 for a non-existent user
    }
}
# AI Model Configuration
AI_MODEL_FAST = "openrouter/auto"
AI_MODEL_RELIABLE = "openrouter/openrouter/auto" # Or another reliable free model

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Component A: Image EXIF Analyzer ---

def get_exif_data(image_path):
    """
    Extracts EXIF data from an image file.
    Processes iteratively to avoid loading entire file into memory.
    """
    exif_data = {}
    try:
        # Open image iteratively
        with Image.open(image_path) as img:
            # Check if image has EXIF data
            if 'exif' in img.info:
                exif_bytes = img.info['exif']
                # PIL's exif_bytes is already somewhat processed, but we can parse it further
                # For true iterative processing without loading all exif, it's complex.
                # PIL's approach is generally efficient for metadata.
                # We'll rely on PIL's metadata extraction here.
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
    """
    Formats extracted EXIF data into a structured string or dictionary.
    """
    formatted_info = {
        "file_path": image_path,
        "timestamps": {},
        "camera_info": {},
        "gps_coordinates": None,
        "software": None
    }

    # Extract common tags
    for tag, value in exif_data.items():
        if tag in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
            try:
                formatted_info["timestamps"][tag] = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').isoformat()
            except ValueError:
                formatted_info["timestamps"][tag] = str(value) # Fallback if format is unexpected
        elif tag in ('Model', 'Make'):
            formatted_info["camera_info"][tag] = str(value)
        elif tag == 'Software':
            formatted_info["software"] = str(value)
        elif tag == 'GPSInfo':
            # Extract GPS coordinates if available
            if 'GPSLatitude' in value and 'GPSLongitude' in value:
                lat_deg = value['GPSLatitude']
                lat_ref = value['GPSLatitudeRef']
                lon_deg = value['GPSLongitude']
                lon_ref = value['GPSLongitudeRef']

                # Convert degrees, minutes, seconds to decimal degrees
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

    # Ensure at least one timestamp is present if any were found
    if not formatted_info["timestamps"] and "DateTime" in exif_data:
         try:
            formatted_info["timestamps"]["DateTime"] = datetime.strptime(str(exif_data["DateTime"]), '%Y:%m:%d %H:%M:%S').isoformat()
         except ValueError:
            formatted_info["timestamps"]["DateTime"] = str(exif_data["DateTime"])

    # Remove empty fields for cleaner output
    formatted_info = {k: v for k, v in formatted_info.items() if v}
    if "timestamps" in formatted_info and not formatted_info["timestamps"]:
        del formatted_info["timestamps"]
    if "camera_info" in formatted_info and not formatted_info["camera_info"]:
        del formatted_info["camera_info"]

    return formatted_info

async def scan_images_for_exif(folder_path):
    """
    Scans a designated folder for images and extracts EXIF data.
    Returns a list of structured EXIF data dictionaries.
    """
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

# --- Component B: Asynchronous Username Tracker ---

async def check_username_on_site(session, username, site_config):
    """
    Checks if a username exists on a single target site.
    Returns the profile URL if found, None otherwise.
    """
    url_template = site_config['url_template']
    url = url_template.format(username=username)
    not_found_indicator = site_config.get('not_found_indicator', {})

    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                # Check for text indicators if status is OK
                if 'text_contains' in not_found_indicator:
                    content = await response.text()
                    if not_found_indicator['text_contains'] in content:
                        logging.debug(f"Username '{username}' not found on {url} (text indicator).")
                        return None
                    else:
                        logging.debug(f"Username '{username}' found on {url}.")
                        return url
                else:
                    logging.debug(f"Username '{username}' found on {url} (status 200).")
                    return url
            elif 'status_code' in not_found_indicator and response.status == not_found_indicator['status_code']:
                logging.debug(f"Username '{username}' not found on {url} (status code {response.status}).")
                return None
            else:
                logging.debug(f"Username '{username}' check on {url} returned status {response.status}.")
                return None
    except aiohttp.ClientError as e:
        logging.warning(f"Network error checking {url}: {e}")
        return None
    except asyncio.TimeoutError:
        logging.warning(f"Timeout checking {url} for username '{username}'.")
        return None
    except Exception as e:
        logging.error(f"Unexpected error checking {url}: {e}")
        return None

async def track_username(username):
    """
    Tracks a username across configured sites concurrently.
    Returns a list of verified profile URLs.
    """
    logging.info(f"Tracking username: '{username}'")
    active_footprint = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for site_name, config in USERNAME_TRACKER_SITES.items():
            tasks.append(check_username_on_site(session, username, config))

        results = await asyncio.gather(*tasks)

        for url in results:
            if url:
                active_footprint.append(url)

    logging.info(f"Username '{username}' found on {len(active_footprint)} sites: {active_footprint}")
    return active_footprint

# --- Component C: Smart AI Synthesis Layer (OpenRouter) ---

async def synthesize_findings_with_ai(image_data, username_footprint):
    """
    Synthesizes findings from image analysis and username tracking using OpenRouter.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("\n" + "="*60)
        print("  Error: OPENROUTER_API_KEY environment variable not detected.")
        print("  Skipping AI analysis phase.")
        print("="*60 + "\n")
        return {"error": "API key not found"}

    logging.info("Synthesizing findings with AI...")

    # Prepare the prompt
    prompt_parts = ["Analyze the following intelligence data:\n\n"]

    if image_data:
        prompt_parts.append("--- Image EXIF Data ---\n")
        for item in image_data:
            prompt_parts.append(json.dumps(item, indent=2))
            prompt_parts.append("\n")
    else:
        prompt_parts.append("--- No Image EXIF Data Found ---\n\n")

    if username_footprint:
        prompt_parts.append("--- Username Footprint ---\n")
        for url in username_footprint:
            prompt_parts.append(f"- {url}\n")
    else:
        prompt_parts.append("--- No Username Footprint Found ---\n\n")

    prompt_parts.append("\nProvide a concise intelligence summary, highlighting potential connections or points of interest.")

    full_prompt = "".join(prompt_parts)

    # Use a fast and free model
    model_to_use = AI_MODEL_FAST

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model_to_use,
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 500, # Limit response length
        "temperature": 0.3 # Lower temperature for more factual, less creative output
    }
    openrouter_api_url = "https://openrouter.ai/api/v1/chat/completions"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(openrouter_api_url, headers=headers, json=data, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_summary = result.get('choices', [{}])[0].get('message', {}).get('content', 'AI analysis failed to produce content.')
                    logging.info("AI synthesis complete.")
                    return {"ai_summary": ai_summary}
                else:
                    error_details = await response.text()
                    logging.error(f"OpenRouter API error: {response.status} - {error_details}")
                    return {"error": f"AI analysis failed: {response.status} - {error_details}"}
    except aiohttp.ClientError as e:
        logging.error(f"Network error communicating with OpenRouter: {e}")
        return {"error": f"Network error during AI analysis: {e}"}
    except asyncio.TimeoutError:
        logging.error("OpenRouter API request timed out.")
        return {"error": "AI analysis timed out."}
    except Exception as e:
        logging.error(f"Unexpected error during AI synthesis: {e}")
        return {"error": f"An unexpected error occurred during AI analysis: {e}"}

# --- Main Orchestration ---

async def main():
    """Main function to orchestrate the intel portal components."""
    print("Starting Intel Portal...")

    # --- Component A: Image EXIF Analysis ---
    print(f"\n[+] Starting Image EXIF Analysis in '{IMAGE_SCAN_FOLDER}'...")
    # Ensure the scan folder exists
    if not os.path.exists(IMAGE_SCAN_FOLDER):
        os.makedirs(IMAGE_SCAN_FOLDER)
        print(f"Created directory: {IMAGE_SCAN_FOLDER}")
    image_data = await scan_images_for_exif(IMAGE_SCAN_FOLDER)
    print(f"[+] Image EXIF Analysis Complete. Found data for {len(image_data)} images.")

    # --- Component B: Username Tracking ---
    username_to_track = input("\nEnter username handle to track: ").strip()
    if not username_to_track:
        print("No username entered. Skipping username tracking.")
        username_footprint = []
    else:
        print(f"\n[+] Starting Username Tracking for '{username_to_track}'...")
        username_footprint = await track_username(username_to_track)
        print(f"[+] Username Tracking Complete. Found {len(username_footprint)} profiles.")

    # --- Component C: AI Synthesis ---
    print("\n[+] Initiating AI Synthesis Layer...")
    ai_results = await synthesize_findings_with_ai(image_data, username_footprint)

    # --- Output and Saving ---
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
        for url in username_footprint:
            print(f"- {url}")
    else:
        print("\n--- No Username Footprint Found ---")

    if "error" in ai_results:
        print(f"\n--- AI Analysis Status ---")
        print(f"{ai_results['error']}")
    elif ai_results.get("ai_summary"):
        print("\n--- AI Synthesis Summary ---")
        print(ai_results["ai_summary"])
    else:
        print("\n--- AI Analysis Status ---")
        print("AI analysis was skipped or failed to produce a summary.")

    print("\n" + "="*60)
    print("Report generation complete.")

    # Optionally save raw data to a file
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
            logging.error(f"Failed to save raw data to file: {e}")

if __name__ == "__main__":
    # Ensure necessary libraries are installed
    try:
        import PIL
        import aiohttp
        import psutil # Although not used in this version, good to keep for future modularity
    except ImportError as e:
        print(f"Error: Missing required library - {e}")
        print("Please install required libraries using: pip install Pillow aiohttp")
        sys.exit(1)

    # Create image scan folder if it doesn't exist
    if not os.path.exists(IMAGE_SCAN_FOLDER):
        try:
            os.makedirs(IMAGE_SCAN_FOLDER)
            print(f"Created directory for image scanning: {IMAGE_SCAN_FOLDER}")
        except OSError as e:
            print(f"Error creating directory {IMAGE_SCAN_FOLDER}: {e}")
            sys.exit(1)

    asyncio.run(main())
