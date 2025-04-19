/**
 * Simplified Authentication JS for FSU Course Scraper
 * No socket dependencies
 */

console.log('Loading simplified auth.js...');

// Simple state tracking
const AUTH_STATE = {
  debugMode: true  // Enable logging
};

/**
 * Debug logger that won't spam the console
 */
function logDebug(message) {
  if (AUTH_STATE.debugMode) {
    console.log(`[AUTH] ${message}`);
  }
}

// Initialize event listeners when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  logDebug('DOM loaded - initializing auth system');
  
  // Clear any lingering localStorage auth state
  localStorage.removeItem('auth_pending');
  localStorage.removeItem('auth_start_time');
});

// Export functions for debugging
window.debugAuth = {
  getState: () => ({ ...AUTH_STATE }),
  clearState: () => {
    localStorage.removeItem('auth_pending');
    localStorage.removeItem('auth_start_time');
    return 'Auth state cleared';
  }
};

// Page load handler
window.addEventListener('load', function() {
  logDebug('Page load complete - auth system ready');
});
