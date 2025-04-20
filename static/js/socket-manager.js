/**
 * Socket connection manager for FSU Course Scraper
 * Maintains a persistent WebSocket connection across page navigations
 */

// Main connection object and state
const SocketManager = {
    // Connection state
    connected: false,
    username: null,
    socket: null,
    connectionAttempts: 0,
    maxReconnectAttempts: 10,
    
    // Track notification visibility to avoid duplicates
    lastNotifications: {},
    
    // Initialize the socket connection
    init: function(username) {
        console.log('Initializing SocketManager for', username);
        this.username = username;
        
        // Check if we already showed welcome message this session
        const welcomeShown = sessionStorage.getItem('welcome_shown');
        const lastConnected = sessionStorage.getItem('socket_connected_at');
        
        // Connect to socket server
        this.connect();
        
        // Set up page unload handler to save state
        window.addEventListener('beforeunload', () => {
            if (this.connected) {
                sessionStorage.setItem('socket_connected_at', Date.now());
            }
        });
        
        // If this isn't the first page load this session, don't show welcome again
        if (welcomeShown && lastConnected) {
            const timeSinceConnected = Date.now() - parseInt(lastConnected);
            if (timeSinceConnected < 60000) { // Within last minute
                console.log('Recent connection detected, suppressing welcome message');
                this.suppressNextWelcome = true;
            }
        }
        
        return this;
    },
    
    // Connect to the socket server
    connect: function() {
        if (this.socket) {
            console.log('Socket already exists, checking state...');
            
            // If already connected, no need to reconnect
            if (this.socket.connected) {
                console.log('Socket already connected');
                this.connected = true;
                return;
            }
            
            // If connecting or reconnecting, wait
            if (this.socket.connecting) {
                console.log('Socket is currently connecting');
                return;
            }
            
            // Otherwise, disconnect the old socket
            this.socket.close();
            this.socket = null;
        }
        
        // Get socket URL from current page
        const socketUrl = window.location.protocol + '//' + window.location.host;
        console.log('Connecting to socket server at:', socketUrl);
        
        try {
            // Create new socket connection
            this.socket = io(socketUrl, {
                reconnection: true,
                reconnectionAttempts: this.maxReconnectAttempts,
                reconnectionDelay: 1000,
                timeout: 10000,
                transports: ['websocket', 'polling'] // Try WebSocket first, fall back to polling
            });
            
            // Set up event handlers
            this.setupEventHandlers();
            
        } catch (error) {
            console.error('Failed to create socket:', error);
            this.connected = false;
            
            // Try again in 5 seconds
            setTimeout(() => this.connect(), 5000);
        }
    },
    
    // Set up socket event handlers
    setupEventHandlers: function() {
        if (!this.socket) return;
        
        // Connection established
        this.socket.on('connect', () => {
            console.log('Socket connected with ID:', this.socket.id);
            this.connected = true;
            this.connectionAttempts = 0;
            
            // Register for notifications
            this.socket.emit('register', { username: this.username });
            console.log(`Sent registration for user ${this.username}`);
            
            // Update session storage
            sessionStorage.setItem('socket_connected_at', Date.now());
            
            // Show welcome toast unless suppressed
            if (!this.suppressNextWelcome) {
                window.ToastNotifications?.success(
                    'Connected', 
                    'You will receive notifications for course availability and authentication requests.',
                    { duration: 3000 }
                );
                sessionStorage.setItem('welcome_shown', 'true');
            }
            this.suppressNextWelcome = false;
        });
        
        // Disconnection
        this.socket.on('disconnect', (reason) => {
            console.log('Socket disconnected:', reason);
            this.connected = false;
            
            // Show warning if not navigating away
            if (reason !== 'io client disconnect') {
                window.ToastNotifications?.warning(
                    'Disconnected', 
                    'Connection to notification server lost. Attempting to reconnect...',
                    { duration: 0 }
                );
            }
        });
        
        // Reconnection
        this.socket.on('reconnect', (attemptNumber) => {
            console.log('Socket reconnected after', attemptNumber, 'attempts');
            this.connected = true;
            
            // Re-register for notifications
            this.socket.emit('register', { username: this.username });
            console.log(`Re-sent registration for user ${this.username}`);
            
            window.ToastNotifications?.success(
                'Reconnected', 
                'Connection to notification server restored.',
                { duration: 3000 }
            );
        });
        
        // Reconnection attempt
        this.socket.on('reconnect_attempt', (attemptNumber) => {
            console.log('Reconnection attempt:', attemptNumber);
            this.connectionAttempts = attemptNumber;
            
            // If we've tried too many times, show a permanent error
            if (attemptNumber >= this.maxReconnectAttempts) {
                window.ToastNotifications?.error(
                    'Connection Failed', 
                    'Could not connect to notification server after multiple attempts. Please refresh the page.',
                    { duration: 0 }
                );
            }
        });
        
        // Connection error
        this.socket.on('connect_error', (error) => {
            console.error('Socket connection error:', error);
            this.connected = false;
        });
        
        // Handle incoming notifications
        this.socket.on('notification', (data) => {
            console.log('Received notification through socket:', data);
            this.processNotification(data);
        });
        
        // Handle registration response
        this.socket.on('registration_response', (response) => {
            console.log('Registration response received:', response);
            if (response.status === 'success') {
                console.log(`Successfully registered for notifications as ${this.username}`);
            } else {
                console.error('Failed to register for notifications:', response.message);
            }
        });
        
        // Debug event to log all incoming events
        this.socket.onAny((event, ...args) => {
            console.log(`Socket event received: ${event}`, args);
        });
    },
    
    // Process incoming notifications
    processNotification: function(data) {
        // Check if we already showed this notification (avoid duplicates)
        const notificationId = this.getNotificationId(data);
        const now = Date.now();
        if (notificationId) {
            const lastShown = this.lastNotifications[notificationId];
            if (lastShown && (now - lastShown < 10000)) { // 10 seconds de-duplication
                console.log('Suppressing duplicate notification:', notificationId);
                return;
            }
            this.lastNotifications[notificationId] = now;
        }
        
        // Call the notifications display function if available
        if (window.processNotification) {
            console.log('Calling processNotification with data:', data);
            window.processNotification(data);
        } else {
            console.warn('processNotification function not available to display notification');
            
            // Fallback to simple toasts if available
            if (window.ToastNotifications) {
                if (data.type === 'auth') {
                    ToastNotifications.warning(
                        'Authentication Required',
                        data.message,
                        { duration: data.requires_action ? 0 : 10000 }
                    );
                } else if (data.type === 'course_availability') {
                    ToastNotifications.success(
                        'Course Seats Available!',
                        data.message,
                        { duration: 0 }
                    );
                } else {
                    ToastNotifications.info(
                        'Notification',
                        data.message || 'Unknown notification received'
                    );
                }
            }
        }
    },
    
    // Generate a unique ID for a notification for de-duplication
    getNotificationId: function(data) {
        if (!data) return null;
        
        if (data.type === 'auth') {
            return `auth_${data.timestamp || Date.now()}`;
        } else if (data.type === 'course_availability') {
            return `course_${data.course_code}_${data.section}_${data.seats_available}`;
        }
        return null;
    },
    
    // Send a test notification (for debugging)
    sendTestNotification: function() {
        if (!this.connected || !this.socket) {
            console.warn('Cannot send test, not connected');
            window.ToastNotifications?.warning(
                'Cannot Test',
                'Not connected to notification server',
                { duration: 3000 }
            );
            return false;
        }
        
        // Send test notification via socket directly
        this.socket.emit('request_test_notification', { username: this.username });
        console.log('Sent test notification request');
        
        // Also try the HTTP endpoint
        fetch('/socket_test')
            .then(response => response.json())
            .then(data => {
                console.log('Socket test result:', data);
                if (window.ToastNotifications) {
                    ToastNotifications.info(
                        'Socket Test',
                        data.success ? 'Socket test message sent!' : 'Socket test failed: ' + data.error
                    );
                }
            })
            .catch(error => {
                console.error('Test notification error:', error);
                if (window.ToastNotifications) {
                    ToastNotifications.error(
                        'Socket Test Failed',
                        'Could not send test notification: ' + error.message
                    );
                }
            });
            
        return true;
    },
    
    // Get current connection status - useful for debugging
    getStatus: function() {
        return {
            connected: this.connected,
            socketId: this.socket?.id || 'not connected',
            username: this.username,
            lastNotifications: Object.keys(this.lastNotifications).length
        };
    }
};

// Expose getStatus globally for debugging
window.getSocketStatus = function() {
    return SocketManager.getStatus();
};

// Export to global scope
window.SocketManager = SocketManager;
