// Authentication handler for FSU Course Scraper

// IMPORTANT: Don't create a new socket - use the one from base.html
// The socket is already initialized in the base template
console.log("Auth.js loaded, using socket from base template");

// Since socket is already defined in base.html, just add an event listener here
// Handle notifications only for auth-related events to avoid duplicate handlers
socket.on('auth_event', function(data) {
    if (data.type === '2fa_required') {
        showAuthOverlay();
    } else if (data.type === '2fa_approved') {
        hideAuthOverlay();
        // Display success message
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${data.message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        document.querySelector('.container').prepend(alertDiv);
    }
});

// Function to check if form submission might need 2FA
function checkFormAuth(formElement) {
    // Get the username if it exists in the form
    const usernameInput = formElement.querySelector('[name="username"]');
    const username = usernameInput ? usernameInput.value : null;
    
    if (username) {
        // Check if 2FA might be needed
        fetch('/api/check_auth', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `username=${encodeURIComponent(username)}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'auth_required') {
                showAuthOverlay();
            }
        })
        .catch(error => console.error('Error checking auth:', error));
    }
    
    // Always show overlay on forms that might require authentication
    const sensitiveActions = ['add_course', 'monitor_course', 'view_courses'];
    if (formElement.action) {
        const action = formElement.action.toLowerCase();
        if (sensitiveActions.some(term => action.includes(term))) {
            showAuthOverlay();
        }
    }
}

// Override fetch for monitoring API calls
const originalFetch = window.fetch;
window.fetch = function() {
    const url = arguments[0];
    if (typeof url === 'string' && url.includes('/toggle_monitor')) {
        return originalFetch.apply(this, arguments)
            .then(response => {
                if (!response.ok && response.status === 401) {
                    return response.json().then(data => {
                        if (data.auth_required) {
                            // Show the overlay if authentication is needed
                            showAuthOverlay();
                            
                            // Return a promise that will retry the request after auth completion
                            return new Promise((resolve) => {
                                // Listen for auth completion
                                const authCompleteHandler = function(event) {
                                    if (event.data === '2fa_approved') {
                                        window.removeEventListener('message', authCompleteHandler);
                                        // Retry the request after a short delay
                                        setTimeout(() => {
                                            originalFetch.apply(window, arguments)
                                                .then(resolve)
                                                .catch(error => {
                                                    console.error('Retry failed:', error);
                                                    resolve(new Response(JSON.stringify({
                                                        error: 'Failed to authenticate'
                                                    }), { status: 500 }));
                                                });
                                        }, 1000);
                                    }
                                };
                                
                                window.addEventListener('message', authCompleteHandler);
                            });
                        }
                        
                        // If it's another error, just return the response
                        return Promise.reject(new Error(data.error || 'Authentication error'));
                    });
                }
                return response;
            });
    }
    
    // For all other requests, use the original fetch
    return originalFetch.apply(this, arguments);
};

// Add event listeners to all forms
document.addEventListener('DOMContentLoaded', function() {
    // Find toggle monitoring buttons and attach handlers
    const toggleButtons = document.querySelectorAll('.toggle-monitor-btn');
    toggleButtons.forEach(button => {
        const originalHandler = button.onclick;
        button.onclick = function(e) {
            // Let the original handler run
            if (originalHandler) {
                originalHandler.call(this, e);
            }
        };
    });

    // Add listeners to forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // For non-login forms that might require authentication
            if (!form.action.includes('login')) {
                checkFormAuth(form);
            }
        });
    });
});
