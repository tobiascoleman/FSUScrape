/**
 * Simplified Authentication JS for FSU Course Scraper
 * Only shows auth notifications when explicitly instructed by server
 */

console.log('Loading simplified auth.js...');

// Simple state tracking - don't persist in localStorage anymore
const AUTH_STATE = {
  isShowingNotification: false,
  lastShowTime: null,
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

/**
 * Show the 2FA authentication notification
 */
function showAuthOverlay() {
  // Only show if not already showing
  if (AUTH_STATE.isShowingNotification) {
    logDebug('Auth overlay already visible, not showing again');
    return;
  }
  
  const notification = document.getElementById('auth-notification');
  if (!notification) {
    console.error('Auth notification element not found!');
    return;
  }
  
  logDebug('Showing auth notification');
  
  // Update UI
  notification.classList.add('show');
  document.body.classList.add('showing-auth');
  
  // Update state
  AUTH_STATE.isShowingNotification = true;
  AUTH_STATE.lastShowTime = Date.now();
}

/**
 * Hide the 2FA authentication notification
 */
function hideAuthOverlay() {
  const notification = document.getElementById('auth-notification');
  if (!notification) {
    console.error('Auth notification element not found!');
    return;
  }
  
  logDebug('Hiding auth notification');
  
  // Update UI
  notification.classList.remove('show');
  document.body.classList.remove('showing-auth');
  
  // Update state
  AUTH_STATE.isShowingNotification = false;
}

// Initialize event listeners when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  logDebug('DOM loaded - initializing auth system');
  
  // Set up dismiss button handler
  const dismissButton = document.getElementById('dismiss-auth-btn');
  if (dismissButton) {
    dismissButton.addEventListener('click', function() {
      logDebug('User clicked dismiss button');
      hideAuthOverlay();
    });
  } else {
    console.warn('Dismiss button not found in DOM');
  }
  
  // No more localStorage persistence
  // No more automatic showing of auth overlay on page load
  
  // Handle ESC key to dismiss
  document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape' && AUTH_STATE.isShowingNotification) {
      logDebug('User pressed ESC key to dismiss');
      hideAuthOverlay();
    }
  });
  
  // Clear any lingering localStorage auth state
  localStorage.removeItem('auth_pending');
  localStorage.removeItem('auth_start_time');
});

// CRITICAL: Only listen for socket.io events that come from the server
if (typeof socket !== 'undefined') {
  logDebug('Setting up socket.io listeners');
  
  // Listen for notification events from server
  socket.on('notification', function(data) {
    logDebug(`Received socket notification: ${data.type}`);
    
    if (data.type === '2fa_required') {
      logDebug('Server requested to show 2FA notification');
      showAuthOverlay();
    } else if (data.type === '2fa_approved') {
      logDebug('Server indicated 2FA is approved');
      hideAuthOverlay();
    }
  });
  
  // Direct commands from server - highest priority
  socket.on('direct_message', function(data) {
    logDebug(`Received direct message: ${data.action}`);
    
    if (data.action === 'show_auth_overlay_now') {
      logDebug('Server directly commanded to show auth overlay');
      showAuthOverlay();
    } else if (data.action === 'hide_auth_overlay') {
      logDebug('Server directly commanded to hide auth overlay');
      hideAuthOverlay();
    }
  });
  
  // When socket.io reconnects, check if we need to reset auth state
  socket.on('reconnect', function() {
    logDebug('Socket reconnected - resetting auth state');
    if (AUTH_STATE.isShowingNotification) {
      // If reconnection happens while notification is showing,
      // it's safer to hide it as we don't know the current server state
      hideAuthOverlay();
    }
  });
}

// Export functions for debugging and direct use
window.debugAuth = {
  showAuthOverlay: showAuthOverlay,
  hideAuthOverlay: hideAuthOverlay,
  getState: () => ({ ...AUTH_STATE }),
  clearState: () => {
    localStorage.removeItem('auth_pending');
    localStorage.removeItem('auth_start_time');
    AUTH_STATE.isShowingNotification = false;
    return 'Auth state cleared';
  }
};

// IMPORTANT: Remove any page load triggers that might show auth overlay unnecessarily
window.addEventListener('load', function() {
  logDebug('Page load complete - auth system ready');
});
