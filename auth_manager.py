import time
import threading
import requests
import json
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

# Thread-safe cookie cache with expiration times
# Format: {username: {'cookies': [...], 'expiry': datetime}}
COOKIE_CACHE = {}
CACHE_LOCK = threading.Lock()

# Track ongoing refresh operations to prevent duplicates
REFRESH_IN_PROGRESS = {}
REFRESH_LOCKS = {}

# Cookie expiration time (shorter than default FSU session)
COOKIE_EXPIRY = timedelta(minutes=30)  # Reduced from 2 hours

# IMPORTANT: Global login lock to ensure only one chromedriver at a time
# This lock will be used whenever a login attempt is made
GLOBAL_LOGIN_LOCK = threading.Lock()

# System-wide busy status tracking
SYSTEM_BUSY = False
SYSTEM_BUSY_LOCK = threading.Lock()

def set_system_busy(busy_status):
    """Set the system-wide busy status (used for monitoring)"""
    global SYSTEM_BUSY
    with SYSTEM_BUSY_LOCK:
        SYSTEM_BUSY = busy_status
        print(f"System busy status set to: {SYSTEM_BUSY}")

def is_system_busy():
    """Check if the system is currently busy with background operations"""
    with SYSTEM_BUSY_LOCK:
        return SYSTEM_BUSY

def validate_cookies(cookies, username=None):
    """Test if cookies are still valid by accessing the entry page with improved reliability."""
    if username:
        debug_prefix = f"[{username}]"
    else:
        debug_prefix = "[cookie-check]"
        
    try:
        if not cookies:
            print(f"{debug_prefix} No cookies provided for validation")
            return False
            
        # Create a proper cookie header
        headers = {
            "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Most reliable endpoint first
        endpoint = "https://fsu.collegescheduler.com/entry"
        
        try:
            print(f"{debug_prefix} Validating cookies against {endpoint}...")
            response = requests.get(endpoint, headers=headers, timeout=5)
            
            if response.status_code == 200:
                # Check for specific content that indicates a successful login
                if "Choose a Term" in response.text or "Calendar Options" in response.text or "Term-options" in response.text:
                    print(f"{debug_prefix} Cookies are valid (confirmed with page content)")
                    return True
                    
                # If we can't verify with content, status code 200 is still promising
                print(f"{debug_prefix} Cookies seem valid (status 200, but couldn't verify content)")
                return True
                
            elif response.status_code in (401, 403, 302):
                # 302 redirect to login page is a common sign of invalid cookies
                print(f"{debug_prefix} Authentication rejected: {response.status_code}")
                return False
            
            # For any other status, be cautious
            print(f"{debug_prefix} Unexpected status code: {response.status_code}")
            return False
                
        except requests.exceptions.RequestException as e:
            print(f"{debug_prefix} Request failed: {e}")
            return False
            
    except Exception as e:
        print(f"{debug_prefix} Cookie validation failed with error: {e}")
        return False

def get_valid_cookies(username, password, notify_callback=None, force_refresh=False):
    """
    Get valid cookies for FSU services, with robust caching and refresh logic.
    
    This function ensures only one thread performs a login for a user at a time,
    and waiting threads check for valid cookies before attempting their own login.
    """
    debug_prefix = f"[{username}]"
    print(f"{debug_prefix} Cookie request received (force_refresh={force_refresh})")
    
    # STEP 1: Quick check for valid cached cookies (no locks needed)
    if not force_refresh:
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (initial check)")
                        return cache_entry['cookies']
                    print(f"{debug_prefix} Found cached cookies but they're invalid (initial check)")
    
    # STEP 2: Create a lock for this user if needed
    if username not in REFRESH_LOCKS:
        with CACHE_LOCK:
            if username not in REFRESH_LOCKS:
                REFRESH_LOCKS[username] = threading.Lock()
    
    # STEP 3: Check if refresh is already in progress and wait if needed
    refresh_in_progress = False
    with CACHE_LOCK:
        refresh_in_progress = username in REFRESH_IN_PROGRESS and REFRESH_IN_PROGRESS[username]
    
    if refresh_in_progress:
        print(f"{debug_prefix} Refresh already in progress, waiting...")
        wait_start = time.time()
        
        # Wait for the refresh to complete or time out
        while True:
            with CACHE_LOCK:
                if not (username in REFRESH_IN_PROGRESS and REFRESH_IN_PROGRESS[username]):
                    print(f"{debug_prefix} Another thread completed refresh")
                    break
            
            # Check timeout
            if time.time() - wait_start > 60:
                print(f"{debug_prefix} Timeout waiting for refresh")
                break
                
            time.sleep(1)
        
        # Check for valid cookies after waiting
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (after waiting)")
                        return cache_entry['cookies']
                    print(f"{debug_prefix} Found cached cookies but they're invalid (after waiting)")
    
    # STEP 4: Try to acquire the user lock with timeout
    print(f"{debug_prefix} Attempting to acquire user lock")
    user_lock_acquired = REFRESH_LOCKS[username].acquire(timeout=10)
    
    if not user_lock_acquired:
        print(f"{debug_prefix} Failed to acquire user lock, checking cached cookies")
        # If we can't get the lock, try to use cached cookies as a fallback
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (lock acquisition failed)")
                        return cache_entry['cookies']
        # If we can't get the lock and don't have valid cached cookies, fail
        raise Exception(f"{debug_prefix} Failed to acquire user lock and no valid cookies available")
    
    # We now have the user lock
    try:
        # STEP 5: Check again for valid cookies now that we have the user lock
        if not force_refresh:
            with CACHE_LOCK:
                if username in COOKIE_CACHE:
                    cache_entry = COOKIE_CACHE[username]
                    if datetime.now() < cache_entry['expiry']:
                        if validate_cookies(cache_entry['cookies'], username):
                            print(f"{debug_prefix} Using valid cached cookies (after user lock)")
                            return cache_entry['cookies']
        
        # STEP 6: Mark that we're starting a refresh
        with CACHE_LOCK:
            REFRESH_IN_PROGRESS[username] = True
        
        try:
            # STEP 7: Acquire the global login lock (only one browser session at a time)
            print(f"{debug_prefix} Attempting to acquire global login lock")
            global_lock_acquired = GLOBAL_LOGIN_LOCK.acquire(timeout=120)
            
            if not global_lock_acquired:
                print(f"{debug_prefix} Failed to acquire global login lock")
                raise Exception("Failed to acquire global login lock - another login is in progress")
            
            # We now have the global login lock
            try:
                # STEP 8: One last check before starting browser (very important!)
                if not force_refresh:
                    with CACHE_LOCK:
                        if username in COOKIE_CACHE:
                            cache_entry = COOKIE_CACHE[username]
                            if datetime.now() < cache_entry['expiry']:
                                if validate_cookies(cache_entry['cookies'], username):
                                    print(f"{debug_prefix} Using valid cached cookies (after global lock)")
                                    return cache_entry['cookies']
                
                # STEP 9: No valid cookies found, perform login
                print(f"{debug_prefix} No valid cookies found, starting login process")
                
                # Notify frontend that 2FA will be required
                if notify_callback:
                    notify_callback(username, "2FA authentication required. Please check your phone.", notification_type="2fa_required")
                
                # Start the browser and perform login
                cookies = perform_login(username, password)
                
                # Validate the cookies
                if not validate_cookies(cookies, username):
                    raise Exception(f"{debug_prefix} Login succeeded but cookies are invalid")
                
                # Cache the new cookies
                with CACHE_LOCK:
                    COOKIE_CACHE[username] = {
                        'cookies': cookies,
                        'expiry': datetime.now() + COOKIE_EXPIRY
                    }
                
                # Notify frontend that 2FA is complete
                if notify_callback:
                    notify_callback(username, "Authentication successful", notification_type="2fa_approved")
                
                print(f"{debug_prefix} Login successful, new cookies cached")
                return cookies
                
            finally:
                # STEP 10: Always release the global login lock
                print(f"{debug_prefix} Releasing global login lock")
                GLOBAL_LOGIN_LOCK.release()
                
        finally:
            # STEP 11: Clear the refresh-in-progress flag
            with CACHE_LOCK:
                REFRESH_IN_PROGRESS[username] = False
            
    finally:
        # STEP 12: Always release the user lock
        print(f"{debug_prefix} Releasing user lock")
        REFRESH_LOCKS[username].release()
        
        # STEP 13: Final check for valid cookies before returning
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (final check)")
                        return cache_entry['cookies']
    
    # If we reach here, something went wrong
    raise Exception(f"{debug_prefix} Failed to obtain valid cookies")

def perform_login(username, password, headless=False):
    """Perform the actual login process and handle 2FA."""
    print(f"Starting ChromeDriver for {username}")
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print(f"ChromeDriver initialized for {username}")
        
        # Navigate to login page
        driver.get("https://cas.fsu.edu/cas/login?service=https%3A%2F%2Fwww.my.fsu.edu%2Fc%2Fportal%2Flogin")
        
        # Enter credentials
        userfield = driver.find_element(By.NAME, "username")
        passfield = driver.find_element(By.NAME, "password")
        userfield.send_keys(username)
        passfield.send_keys(password)
        
        # Submit login form
        login_button = driver.find_element(By.NAME, "submit")
        login_button.click()
        
        # Handle 2FA if needed
        time.sleep(5)  # Wait for page to load after login
        
        if "Secured by Duo" in driver.page_source.strip():
            print("2FA detected! Please approve the login on your phone.")
            max_wait = 60  # Maximum wait time in seconds
            start_time = time.time()
            
            while "Secured by Duo" in driver.page_source.strip():
                time.sleep(2)  # Check every 2 seconds
                if time.time() - start_time > max_wait:
                    raise Exception("2FA timeout after 60 seconds")
            
            print("2FA approved!")
            # Notify any waiting UI
            driver.execute_script("window.parent.postMessage('2fa_approved', '*');")
        else:
            # No 2FA prompt, but still notify UI
            driver.execute_script("window.parent.postMessage('2fa_approved', '*');")
        
        # Complete login process
        WebDriverWait(driver, 20).until(lambda d: d.find_element(By.ID, "dont-trust-browser-button")).click()
        WebDriverWait(driver, 20).until(lambda d: d.find_element(
            By.ID, "kgoui_FpageHeader"))
        
        # Navigate to the scheduler to get necessary cookies
        driver.get("https://fsu.collegescheduler.com/entry")
        try:
            WebDriverWait(driver, 20).until(lambda d: d.find_element(By.ID, "Term-options"))
        except Exception as e:
            print(f"Entry page element not found. URL: {driver.current_url}")
            print(f"Page source: {driver.page_source[:500]}...")
            raise
        
        # Give a bit more time for all cookies to be set
        time.sleep(3)
        
        # Get and return cookies
        cookies = driver.get_cookies()
        print(f"Got {len(cookies)} cookies from login process for {username}")
        return cookies
    
    except Exception as e:
        print(f"Login failed for {username}: {str(e)}")
        raise
    
    finally:
        if driver:
            print(f"Closing ChromeDriver for {username}")
            driver.quit()

def get_cookie_header(username, password, notify_callback=None):
    """Get cookies and format them as a header string for API requests."""
    cookies = get_valid_cookies(username, password, notify_callback)
    # Fix syntax error in list comprehension - removed extra parentheses
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)

def clear_cookie_cache(username=None):
    """Clear cookie cache for a specific user or all users."""
    with CACHE_LOCK:
        if username:
            if username in COOKIE_CACHE:
                del COOKIE_CACHE[username]
                print(f"Cleared cached cookies for {username}")
        else:
            COOKIE_CACHE.clear()
            print("Cleared all cached cookies")

# Example usage
if __name__ == "__main__":
    username = input("Username: ")
    password = input("Password: ")
    
    # Get cookies
    cookies = get_valid_cookies(username, password)
    print(f"Got {len(cookies)} cookies")
    
    # Test cookie validation
    is_valid = validate_cookies(cookies)
    print(f"Cookies valid: {is_valid}")
    
    # Test API call with cookies
    headers = {"Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)}
    test_response = requests.get("https://fsu.collegescheduler.com/api/terms", headers=headers)
    print(f"API test response: {test_response.status_code}")
    print(test_response.text[:100] if test_response.status_code == 200 else "Failed")
