/**
 * Toast Notification System
 * Creates non-invasive notifications that appear and disappear automatically
 */

const ToastNotifications = {
    // Container for all notifications
    container: null,
    toastCount: 0,
    maxToasts: 5,
    
    // Initialize the notification system
    init: function() {
        // Create container if it doesn't exist
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container position-fixed top-0 end-0 p-3';
            this.container.style.zIndex = '1080';
            document.body.appendChild(this.container);
            console.log('Toast notification container created');
        }
        return this;
    },
    
    // Create a new toast notification
    create: function(title, message, options = {}) {
        if (!this.container) this.init();
        
        // Default options
        const defaults = {
            type: 'info',
            duration: 5000,
            closable: true,
            sound: false,
            onClick: null
        };
        
        const settings = { ...defaults, ...options };
        
        // Manage toast count
        if (this.toastCount >= this.maxToasts) {
            const oldestToast = this.container.firstChild;
            if (oldestToast) {
                this.container.removeChild(oldestToast);
                this.toastCount--;
            }
        }
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast mb-3 fade show bg-${settings.type === 'error' ? 'danger' : settings.type}`;
        toast.style.borderColor = `var(--bs-${settings.type === 'error' ? 'danger' : settings.type})`;
        
        // Build toast content
        toast.innerHTML = `
            <div class="toast-header bg-${settings.type === 'error' ? 'danger' : settings.type} text-white">
                <strong class="me-auto">${title}</strong>
                <small>${new Date().toLocaleTimeString()}</small>
                ${settings.closable ? '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>' : ''}
            </div>
            <div class="toast-body bg-${settings.type === 'error' ? 'danger' : settings.type} text-white toast-message">
                ${message}
            </div>
        `;
        
        // Add click handler if provided
        if (settings.onClick && typeof settings.onClick === 'function') {
            toast.style.cursor = 'pointer';
            toast.addEventListener('click', function(e) {
                // Don't trigger if they clicked the close button
                if (e.target.classList.contains('btn-close')) return;
                settings.onClick(e);
            });
        }
        
        // Play sound if requested
        if (settings.sound && window.SimpleSounds) {
            if (settings.type === 'success') {
                SimpleSounds.success();
            } else if (settings.type === 'warning' || settings.type === 'error') {
                SimpleSounds.alert();
            } else {
                SimpleSounds.notification();
            }
        }
        
        // Add to container
        this.container.appendChild(toast);
        this.toastCount++;
        
        // Auto-dismiss if duration > 0
        if (settings.duration > 0) {
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => {
                    if (toast.parentNode === this.container) {
                        this.container.removeChild(toast);
                        this.toastCount--;
                    }
                }, 300); // Allow for fade out animation
            }, settings.duration);
        }
        
        return toast;
    },
    
    // Helper methods for different notification types
    info: function(title, message, options = {}) {
        return this.create(title, message, { ...options, type: 'info' });
    },
    
    success: function(title, message, options = {}) {
        return this.create(title, message, { ...options, type: 'success' });
    },
    
    warning: function(title, message, options = {}) {
        return this.create(title, message, { ...options, type: 'warning' });
    },
    
    error: function(title, message, options = {}) {
        return this.create(title, message, { ...options, type: 'error' });
    },
    
    // Clear all notifications
    clear: function() {
        if (this.container) {
            while (this.container.firstChild) {
                this.container.removeChild(this.container.firstChild);
            }
            this.toastCount = 0;
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    ToastNotifications.init();
});

// Export to global scope
window.ToastNotifications = ToastNotifications;
