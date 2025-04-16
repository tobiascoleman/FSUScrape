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
COOKIE_CACHE = {}
CACHE_LOCK = threading.Lock()

# Track ongoing refresh operations to prevent duplicates
REFRESH_IN_PROGRESS = {}
REFRESH_LOCKS = {}

# Cookie expiration time
COOKIE_EXPIRY = timedelta(minutes=30)

# Global login lock to ensure only one chromedriver at a time
GLOBAL_LOGIN_LOCK = threading.Lock()

# Socket.io reference (set by app.py)
socketio = None

def setup_socketio(socketio_instance):
    """Set up socketio reference for sending notifications"""
    global socketio
    socketio = socketio_instance
    print("Socket.IO reference set up successfully")

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

def send_2fa_notification(username, message="2FA authentication required. Please check your phone."):
    """Send 2FA notification directly via socket.io"""
    if socketio is None:
        print(f"[{username}] ❌ Cannot send notification: Socket.IO not initialized")
        return False
        
    try:
        print(f"[{username}] 📱 SENDING 2FA NOTIFICATION: {message}")
        
        # Send via socket.io with high priority
        socketio.emit('notification', {
            'message': message,
            'type': "2fa_required",
            'priority': True,
            'timestamp': time.time(),
            'id': str(time.time())
        }, namespace='/', room=username)
        
        # Also send direct message for redundancy
        socketio.emit('direct_message', {
            'action': 'show_auth_overlay_now',
            'timestamp': time.time()
        }, namespace='/', room=username)
        
        return True
    except Exception as e:
        print(f"[{username}] ❌ Error sending notification: {str(e)}")
        return False

def validate_cookies(cookies, username=None):
    """Test if cookies are still valid"""
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

def get_valid_cookies(username, password, force_refresh=False):
    """
    Get valid cookies - completely simplified logic.
    """
    debug_prefix = f"[{username}]"
    print(f"{debug_prefix} Cookie request received (force_refresh={force_refresh})")
    
    # STEP 1: Check for valid cached cookies first (no locks needed)
    if not force_refresh:
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (initial check)")
                        return cache_entry['cookies']
                    print(f"{debug_prefix} Found cached cookies but they're invalid")
    
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
        print(f"{debug_prefix} Failed to acquire user lock, checking cached cookies as fallback")
        # If we can't get the lock, try to use cached cookies as a fallback
        with CACHE_LOCK:
            if username in COOKIE_CACHE:
                cache_entry = COOKIE_CACHE[username]
                if datetime.now() < cache_entry['expiry']:
                    if validate_cookies(cache_entry['cookies'], username):
                        print(f"{debug_prefix} Using valid cached cookies (lock acquisition failed)")
                        return cache_entry['cookies']
        print(f"{debug_prefix} Failed to acquire user lock and no valid cached cookies available")
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
                            print(f"{debug_prefix} Using valid cached cookies (after user lock)")
                            return cache_entry['cookies']
        
        # STEP 6: Mark that we're starting a refresh
        with CACHE_LOCK:
            REFRESH_IN_PROGRESS[username] = True
        
        try:
            # STEP 7: Acquire the global login lock
            print(f"{debug_prefix} Attempting to acquire global login lock")
            global_lock_acquired = GLOBAL_LOGIN_LOCK.acquire(timeout=120)
            
            if not global_lock_acquired:
                print(f"{debug_prefix} Failed to acquire global login lock")
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
                                    print(f"{debug_prefix} Using valid cached cookies (after global lock)")
                                    return cache_entry['cookies']
                
                # STEP 9: Perform login - this will send 2FA notification internally
                print(f"{debug_prefix} Starting login process")
                cookies = perform_login(username, password)
                
                # Validate and cache the cookies
                if not validate_cookies(cookies, username):
                    print(f"{debug_prefix} Login succeeded but cookies are invalid")
                    return None
                
                with CACHE_LOCK:
                    COOKIE_CACHE[username] = {
                        'cookies': cookies,
                        'expiry': datetime.now() + COOKIE_EXPIRY
                    }
                
                print(f"{debug_prefix} Login successful, new cookies cached")
                return cookies
                
            finally:
                # Always release the global login lock
                print(f"{debug_prefix} Releasing global login lock")
                GLOBAL_LOGIN_LOCK.release()
                
        finally:
            # Clear the refresh-in-progress flag
            with CACHE_LOCK:
                if username in REFRESH_IN_PROGRESS:
                    REFRESH_IN_PROGRESS[username] = False
            
    finally:
        # Always release the user lock
        print(f"{debug_prefix} Releasing user lock")
        REFRESH_LOCKS[username].release()
    
    # If we reach here, something went wrong
    return None

def perform_login(username, password, headless=False):
    """
    Perform the login process. ALWAYS sends a 2FA notification as part of this process.
    This is the ONLY place that sends 2FA notifications.
    """
    print(f"Starting ChromeDriver for {username}")
    
    # IMMEDIATELY send a 2FA notification - if we're in this function, we always need 2FA
    send_2fa_notification(username)
    
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
        
        # Wait for Duo 2FA to complete
        time.sleep(5)  # Wait for page to load after login
        
        # Wait for Duo to appear and then to disappear (or timeout)
        max_wait = 60  # Maximum wait time in seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if "Secured by Duo" not in driver.page_source.strip():
                break
            time.sleep(2)  # Check every 2 seconds
            
        print("Continuing with login process")
        
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
        
        # Notify UI that login was successful via Socket.IO
        if socketio:
            socketio.emit('notification', {
                'message': "Authentication successful",
                'type': "2fa_approved",
                'timestamp': time.time()
            }, namespace='/', room=username)
        
        return cookies
    
    except Exception as e:
        print(f"Login failed for {username}: {str(e)}")
        raise
    
    finally:
        if driver:
            print(f"Closing ChromeDriver for {username}")
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
                print(f"Cleared cached cookies for {username}")
        else:
            COOKIE_CACHE.clear()
            print("Cleared all cached cookies")

# This function is no longer needed with our simplified approach
# but we'll keep it as a no-op for backward compatibility
def clear_auth_state(username=None):
    """Clear any authentication state (no-op in simplified version)"""
    pass  # We no longer track auth state separately

# Example usage
if __name__ == "__main__":
    username = input("Username: ")
    password = input("Password: ")
    
    # Get cookies
    cookies = get_valid_cookies(username, password)
    print(f"Got {len(cookies) if cookies else 0} cookies")
    
    # Test cookie validation
    if cookies:
        is_valid = validate_cookies(cookies)
        print(f"Cookies valid: {is_valid}")
        
        # Test API call with cookies
        headers = {"Cookie": "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)}
        test_response = requests.get("https://fsu.collegescheduler.com/api/terms", headers=headers)
        print(f"API test response: {test_response.status_code}")
        print(test_response.text[:100] if test_response.status_code == 200 else "Failed")
    else:
        print("Failed to get cookies")
