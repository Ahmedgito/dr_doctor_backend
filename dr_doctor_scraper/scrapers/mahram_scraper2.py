import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime
from typing import List, Optional

# --- Assume these are your imported Pydantic/BaseModels ---
# You will replace the 'print()' statements with your actual MongoDB insert/update logic.

class HospitalModel:
    def __init__(self, **kwargs):
        self.data = kwargs
    def save(self):
        # Placeholder for MongoDB insertion
        print(f"MONGO DB: SAVED HOSPITAL: {self.data.get('name')} | URL: {self.data.get('url')}")
        return self.data.get('url') # Return URL for Doctor Scraping

class DoctorModel:
    def __init__(self, **kwargs):
        self.data = kwargs
    def save(self):
        # Placeholder for MongoDB insertion
        print(f"MONGO DB: SAVED DOCTOR: {self.data.get('name')} | Specialty: {self.data.get('specialty')}")


# --- Configuration ---
BASE_URL = "https://www.marham.pk"
ENTRY_POINT_HOSPITALS = f"{BASE_URL}/hospitals/karachi?page="
PLATFORM_NAME = "Marham"
# ---

## 🚀 Phase 1: Hospital Data Collection & Pagination

def scrape_hospital_listings():
    """Iterates through hospital listing pages and collects basic hospital data."""
    print("--- Starting Phase 1: Scraping Hospital Listings ---")
    page = 1
    hospital_urls = []

    while True:
        url = f"{ENTRY_POINT_HOSPITALS}{page}"
        print(f"Fetching page: {page}")

        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status() # Raise exception for bad status codes
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Selector for the individual hospital card
        hospital_cards = soup.select('.row.shadow-card')

        if not hospital_cards:
            print(f"No more hospital cards found on page {page}. Ending pagination.")
            break

        for card in hospital_cards:
            try:
                # 1. Hospital Name and URL
                name_tag = card.select_one('.hosp_list_selected_hosp_name')
                hospital_name = name_tag.text.strip().replace(', Karachi', '') if name_tag else "N/A"
                hospital_url_path = name_tag['href'] if name_tag and 'href' in name_tag.attrs else None
                hospital_url = f"{BASE_URL}{hospital_url_path}" if hospital_url_path else None
                
                # 2. Hospital Address
                # Selecting the second <p class="text-sm"> that contains the address
                address_p = card.select('p.text-sm')
                address = address_p[1].text.strip() if len(address_p) > 1 else None

                if hospital_url:
                    hospital_data = HospitalModel(
                        name=hospital_name,
                        city="Karachi",
                        address=address,
                        platform=PLATFORM_NAME,
                        url=hospital_url
                    )
                    hospital_urls.append(hospital_data.save()) # Save to DB and collect URL
                    
            except Exception as e:
                print(f"Error processing hospital card on page {page}: {e}")
        
        page += 1
        time.sleep(1) # Be polite, wait a moment between page requests

    return [url for url in hospital_urls if url]


## 🧑‍⚕️ Phase 2: Doctor Data Retrieval (Handling "Load More")

def scrape_doctor_data_from_hospital(hospital_url: str):
    """Scrapes all doctor cards from a single hospital page, handling 'Load More'."""
    print(f"\n--- Starting Phase 2: Scraping Doctors for {hospital_url} ---")
    doctor_id = 0 # Used for dynamic loading/pagination. Initial page is 0.
    all_doctor_cards = []
    
    # We must replicate the AJAX call that the 'Load More' button triggers.
    # By inspecting network traffic, this usually points to a dedicated API endpoint.
    # The common pattern is: /api/hospital-doctors?hospital_id=X&page=Y
    # Since we don't know the exact AJAX API, we'll mimic the *behavior* of the 'Load More' button.
    # The 'Load More' button is likely sending an AJAX request to fetch the next batch.
    
    # 1. Scrape Initial Doctors (First Page Load)
    try:
        response = requests.get(hospital_url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get doctors from the initial page load
        initial_doctors = soup.select('.row.shadow-card')
        all_doctor_cards.extend(initial_doctors)

        # Check for the Load More button to determine if more doctors exist
        load_more_button = soup.select_one('#loadMore')
        
        if load_more_button:
            print(f"Initial {len(initial_doctors)} doctors found. 'Load More' active. Starting AJAX loop...")
            # If the site loads subsequent pages via URL query parameter (e.g., ?skip=10)
            # you would use that. But since there's a button, we assume AJAX.
            
            # --- HYPOTHETICAL AJAX REPLICATE (Most likely scenario for Marham) ---
            # NOTE: For this to work reliably, you must capture the actual AJAX endpoint URL
            # and the payload (e.g., hospital ID and next page number) from your browser's network tab.
            
            # This is the endpoint that likely serves the doctors dynamically:
            ajax_url = f"{BASE_URL}/api/hospital-doctors" # **NOTE: This endpoint is hypothetical!**
            
            # We will use an ID that the button would pass to the server. 
            # Often, the button itself has data attributes. Let's assume the server
            # knows the hospital ID and we just need to pass the skip/page count.
            
            hospital_id_match = re.search(r'hospitals/karachi/.*?/(\w+)', hospital_url)
            hospital_slug = hospital_id_match.group(1) if hospital_id_match else None
            
            # Since the exact API is unknown, we will simulate the dynamic page loading
            # by fetching URLs of the type: hospital-url/doctors?page=X if they exist.
            # *If the below loop fails, you must find the true AJAX endpoint.*

            page_num = 1
            while True:
                # Assuming the site provides a hidden "View All Doctors" or "Doctors" tab/URL
                # structure like: https://www.marham.pk/hospitals/karachi/.../doctors?page=2
                dynamic_url = f"{hospital_url}/doctors?page={page_num}" # Another hypothetical guess!
                
                try:
                    dyn_response = requests.get(dynamic_url, timeout=10)
                    dyn_soup = BeautifulSoup(dyn_response.content, 'html.parser')
                    
                    new_doctors = dyn_soup.select('.row.shadow-card')
                    
                    if not new_doctors:
                        break # Stop when no more doctor cards are found
                    
                    print(f"Found {len(new_doctors)} doctors on dynamic page {page_num}.")
                    all_doctor_cards.extend(new_doctors)
                    page_num += 1
                    time.sleep(1)

                except requests.exceptions.RequestException:
                    break # Stop on error or end of pages
                
        else:
             print(f"Only {len(initial_doctors)} doctors found. No 'Load More' button.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching hospital page {hospital_url}: {e}")
        return

    # 2. Process all collected Doctor Cards
    doctors_count = 0
    for card in all_doctor_cards:
        try:
            # 2.1 Doctor Name and URL
            name_tag = card.select_one('a.dr_profile_opened_from_hospital_profile h3')
            doctor_name = name_tag.text.strip() if name_tag else "N/A"
            profile_url = name_tag.parent['href'] if name_tag and 'href' in name_tag.parent.attrs else None

            # 2.2 Specialty
            specialty_tag = card.select_one('p.mb-0.text-sm')
            specialty = [specialty_tag.text.strip()] if specialty_tag else ["N/A"]
            
            # 2.3 Qualifications (Text like MBBS, MS)
            qualifications_tag = card.select_one('p.text-sm:not(.mb-0)')
            qualifications = qualifications_tag.text.strip() if qualifications_tag else None
            
            # 2.4 Experience (e.g., "20 Yrs")
            experience_tag = card.select_one('.row .col-4:nth-child(2) p.text-bold.text-sm')
            experience = experience_tag.text.strip() if experience_tag else None
            
            if profile_url and doctor_name != "N/A":
                doctor_data = DoctorModel(
                    name=doctor_name,
                    specialty=specialty,
                    city="Karachi", # Inherited
                    hospital=hospital_url, # Link back to the hospital
                    profile_url=profile_url,
                    experience=experience,
                    platform=PLATFORM_NAME
                )
                doctor_data.save()
                doctors_count += 1
                
        except Exception as e:
            # Skip corrupted/malformed cards
            print(f"Skipping malformed doctor card: {e}")
            continue

    print(f"--- Finished scraping {doctors_count} doctors for {hospital_url} ---")


## ⚙️ Main Execution Flow

def run_scraper():
    """Main function to run the entire scraping process."""
    start_time = time.time()
    
    # PHASE 1: Collect all hospital URLs
    hospital_urls_list = scrape_hospital_listings()
    
    print(f"\nCollected a total of {len(hospital_urls_list)} hospital URLs.")
    
    # PHASE 2: Iterate through URLs and scrape doctors for each hospital
    for url in hospital_urls_list:
        scrape_doctor_data_from_hospital(url)
        time.sleep(2) # Longer wait time between hospitals
        
    end_time = time.time()
    print(f"\n\n*** SCAPER FINISHED ***")
    print(f"Total time taken: {end_time - start_time:.2f} seconds.")


# Execute the scraper
# if __name__ == '__main__':
#     run_scraper()