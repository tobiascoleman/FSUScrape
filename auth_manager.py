import time
import threading
import requests
import json
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
import logging
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import notifications

# Set up logging
logger = logging.getLogger('auth_manager')

# Thread-safe cookie cache with expiration times
COOKIE_CACHE = {}
CACHE_LOCK = threading.Lock()

# Track ongoing refresh operations to prevent duplicates
REFRESH_IN_PROGRESS = {}
REFRESH_LOCKS = {}

# Cookie expiration time
COOKIE_EXPIRY = timedelta(minutes=30)

# Global login lock to ensure only one chromedriver at a time
GLOBAL_LOGIN_LOCK = threading.Lock()

def validate_cookies(cookies, username=None):
    """Test if cookies are still valid"""
    if username:
        debug_prefix = f"[{username}]"
    else:
        debug_prefix = "[cookie-check]"
        
    try:
        if not cookies:
            logger.info(f"{debug_prefix} No cookies provided for validation")
            return False
            
        # Create a proper cookie header
        headers = {
            "Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # Most reliable endpoint first
        endpoint = "https://fsu.collegescheduler.com/entry"
        
        try:
            logger.info(f"{debug_prefix} Validating cookies against {endpoint}...")
            response = requests.get(endpoint, headers=headers, timeout=5)
            
            if response.status_code == 200:
                # Check for specific content that indicates a successful login
                if "Choose a Term" in response.text or "Calendar Options" in response.text or "Term-options" in response.text:
                    logger.info(f"{debug_prefix} Cookies are valid (confirmed with page content)")
                    return True
                    
                # If we can't verify with content, status code 200 is still promising
                logger.info(f"{debug_prefix} Cookies seem valid (status 200, but couldn't verify content)")
                return True
                
            elif response.status_code in (401, 403, 302):
                # 302 redirect to login page is a common sign of invalid cookies
                logger.info(f"{debug_prefix} Authentication rejected: {response.status_code}")
                return False
            
            # For any other status, be cautious
            logger.info(f"{debug_prefix} Unexpected status code: {response.status_code}")
            return False
                
        except requests.exceptions.RequestException as e:
            logger.info(f"{debug_prefix} Request failed: {e}")
            return False
            
    except Exception as e:
        logger.info(f"{debug_prefix} Cookie validation failed with error: {e}")
        return False

def get_valid_cookies(username, password, force_refresh=False):
    """
    Get valid cookies - completely simplified logic.
    """
    debug_prefix = f"[{username}]"
    logger.info(f"{debug_prefix} Cookie request received (force_refresh={force_refresh})")
    
    # STEP 1: Check for valid cached cookies first (no locks needed)
    if not force_refresh:
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        logger.info(f"{debug_prefix} Using valid cached cookies (initial check)")
                        return cache_entry['cookies']
                    logger.info(f"{debug_prefix} Found cached cookies but they're invalid")
    
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
        logger.info(f"{debug_prefix} Refresh already in progress, waiting...")
        wait_start = time.time()
        
        # Wait for the refresh to complete or time out
        while True:
            with CACHE_LOCK:
                if not (username in REFRESH_IN_PROGRESS and REFRESH_IN_PROGRESS[username]):
                    logger.info(f"{debug_prefix} Another thread completed refresh")
                    break
            
            # Check timeout
            if time.time() - wait_start > 60:
                logger.info(f"{debug_prefix} Timeout waiting for refresh")
                break
                
            time.sleep(1)
        
        # Check for valid cookies after waiting
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        logger.info(f"{debug_prefix} Using valid cached cookies (after waiting)")
                        return cache_entry['cookies']
                    logger.info(f"{debug_prefix} Found cached cookies but they're invalid (after waiting)")
    
    # STEP 4: Try to acquire the user lock with timeout
    logger.info(f"{debug_prefix} Attempting to acquire user lock")
    user_lock_acquired = REFRESH_LOCKS[username].acquire(timeout=10)
    
    if not user_lock_acquired:
        logger.info(f"{debug_prefix} Failed to acquire user lock, checking cached cookies as fallback")
        # If we can't get the lock, try to use cached cookies as a fallback
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        logger.info(f"{debug_prefix} Using valid cached cookies (lock acquisition failed)")
                        return cache_entry['cookies']
        logger.info(f"{debug_prefix} Failed to acquire user lock and no valid cached cookies available")
        return None
    
    # We now have the user lock
    try:
        # STEP 5: Check again for valid cookies now that we have the user lock
        if not force_refresh:
            with CACHE_LOCK:
                if username in COOKIE_CACHE:
                    cache_entry = COOKIE_CACHE[username]
                    if datetime.now() < cache_entry['expiry']:
                        if validate_cookies(cache_entry['cookies'], username):
                            logger.info(f"{debug_prefix} Using valid cached cookies (after user lock)")
                            return cache_entry['cookies']
        
        # STEP 6: Mark that we're starting a refresh
        with CACHE_LOCK:
            REFRESH_IN_PROGRESS[username] = True
        
        try:
            # STEP 7: Acquire the global login lock
            logger.info(f"{debug_prefix} Attempting to acquire global login lock")
            global_lock_acquired = GLOBAL_LOGIN_LOCK.acquire(timeout=120)
            
            if not global_lock_acquired:
                logger.info(f"{debug_prefix} Failed to acquire global login lock")
                return None
            
            # We now have the global login lock
            try:
                # STEP 8: One last check before starting browser
                if not force_refresh:
                    with CACHE_LOCK:
                        if username in COOKIE_CACHE:
                            cache_entry = COOKIE_CACHE[username]
                            if datetime.now() < cache_entry['expiry']:
                                if validate_cookies(cache_entry['cookies'], username):
                                    logger.info(f"{debug_prefix} Using valid cached cookies (after global lock)")
                                    return cache_entry['cookies']
                
                # STEP 9: Perform login
                logger.info(f"{debug_prefix} Starting login process")
                
                # Send notification that 2FA will be needed
                notifications.send_auth_notification(
                    username, 
                    "2FA authentication required. Please check your device for Duo push notification.",
                    category="warning"
                )
                
                cookies = perform_login(username, password)
                
                # Validate and cache the cookies
                if not validate_cookies(cookies, username):
                    logger.info(f"{debug_prefix} Login succeeded but cookies are invalid")
                    return None
                
                with CACHE_LOCK:
                    COOKIE_CACHE[username] = {
                        'cookies': cookies,
                        'expiry': datetime.now() + COOKIE_EXPIRY
                    }
                
                # Send success notification
                notifications.send_auth_notification(
                    username, 
                    "Authentication successful! Your session is now active.",
                    category="success"
                )
                
                logger.info(f"{debug_prefix} Login successful, new cookies cached")
                return cookies
                
            finally:
                # Always release the global login lock
                logger.info(f"{debug_prefix} Releasing global login lock")
                GLOBAL_LOGIN_LOCK.release()
                
        finally:
            # Clear the refresh-in-progress flag
            with CACHE_LOCK:
                if username in REFRESH_IN_PROGRESS:
                    REFRESH_IN_PROGRESS[username] = False
            
    finally:
        # Always release the user lock
        logger.info(f"{debug_prefix} Releasing user lock")
        REFRESH_LOCKS[username].release()
    
    # If we reach here, something went wrong
    return None

def perform_login(username, password, headless=True): # Set Headless to False for testing
    """
    Perform the login process without socket notifications.
    """
    logger.info(f"Starting ChromeDriver for {username}")
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        logger.info(f"ChromeDriver initialized for {username}")
        
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
        
        # Wait for Duo 2FA to complete
        time.sleep(5)  # Wait for page to load after login
        
        # Wait for Duo to appear and then to disappear (or timeout)
        max_wait = 120  # Maximum wait time in seconds
        start_time = time.time()
        
        try:
            logger.info(f"Waiting for Duo authentication to complete (timeout: 240s)")
            
            # Define a custom expected condition
            def duo_authentication_complete(driver):
                return "Secured by Duo" not in driver.page_source.strip()
            # First wait until it is on the page
            WebDriverWait(driver, 20, poll_frequency=1).until(
                duo_authentication_complete,
                message="Duo authentication timeout - page not found"
            )
            logger.info("Duo authentication page found, waiting for user to approve")
            # Now wait until user approves it
            WebDriverWait(driver, 240, poll_frequency=2).until(
                not duo_authentication_complete,
                message="Duo authentication timeout - user did not complete 2FA"
            )
            
            logger.info("Duo authentication completed successfully")
        except TimeoutException as e:
            logger.error(f"Duo authentication timed out: {e}")
            notifications.send_auth_notification(
                username,
                "2FA authentication timed out. Please try again.",
                category="error"
            )
            raise
            
        logger.info("Continuing with login process")
        
        try:
            # Complete login process
            WebDriverWait(driver, 20).until(lambda d: d.find_element(By.ID, "dont-trust-browser-button")).click()
            WebDriverWait(driver, 20).until(lambda d: d.find_element(
                By.ID, "kgoui_FpageHeader"))
            
            # Navigate to the scheduler to get necessary cookies
            driver.get("https://fsu.collegescheduler.com/entry")
            try:
                WebDriverWait(driver, 20).until(lambda d: d.find_element(By.ID, "Term-options"))
            except Exception as e:
                logger.error(f"Entry page element not found. URL: {driver.current_url}")
                logger.error(f"Page source: {driver.page_source[:500]}...")
                raise
        except TimeoutException:
            # Send error notification
            notifications.send_auth_notification(
                username,
                "2FA authentication timed out. Please try again.",
                category="error"
            )
            raise
            
        # Give a bit more time for all cookies to be set
        time.sleep(3)
        
        # Get and return cookies
        cookies = driver.get_cookies()
        logger.info(f"Got {len(cookies)} cookies from login process for {username}")
        
        return cookies
    
    except Exception as e:
        logger.error(f"Login failed for {username}: {str(e)}")
        # Send error notification
        notifications.send_auth_notification(
            username,
            f"Authentication failed: {str(e)}",
            category="error"
        )
        raise
    
    finally:
        if driver:
            logger.info(f"Closing ChromeDriver for {username}")
            driver.quit()

def get_cookie_header(username, password):
    """Get cookies and format them as a header string for API requests."""
    cookies = get_valid_cookies(username, password)
    if not cookies:
        return None
    return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)

def clear_cookie_cache(username=None):
    """Clear cookie cache for a specific user or all users."""
    with CACHE_LOCK:
        if username:
            if username in COOKIE_CACHE:
                del COOKIE_CACHE[username]
                logger.info(f"Cleared cached cookies for {username}")
        else:
            COOKIE_CACHE.clear()
            logger.info("Cleared all cached cookies")

# This function is no longer needed but we'll keep it as a no-op for backward compatibility
def clear_auth_state(username=None):
    """Clear any authentication state (no-op in simplified version)"""
    pass  # We no longer track auth state separately

# Example usage
if __name__ == "__main__":
    username = input("Username: ")
    password = input("Password: ")
    
    # Get cookies
    cookies = get_valid_cookies(username, password)
    logger.info(f"Got {len(cookies) if cookies else 0} cookies")
    
    # Test cookie validation
    if cookies:
        is_valid = validate_cookies(cookies)
        logger.info(f"Cookies valid: {is_valid}")
        
        # Test API call with cookies
        headers = {"Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)}
        test_response = requests.get("https://fsu.collegescheduler.com/api/terms", headers=headers)
        logger.info(f"API test response: {test_response.status_code}")
        logger.info(test_response.text[:100] if test_response.status_code == 200 else "Failed")


    else:
        logger.info("Failed to get cookies")   
