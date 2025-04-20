"""
Notification system for the FSU Course Scraper application.
Handles sending real-time notifications to the frontend.
"""
import json
import logging
import time
from flask import request, current_app
from flask_socketio import SocketIO, join_room, leave_room, rooms

# Initialize SocketIO instance (will be set by app.py)
socketio = None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('notifications')

# Store username to sid mappings
user_sessions = {}

def init_socketio(app):
    """Initialize the SocketIO instance with the Flask app"""
    global socketio
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    logger.info("SocketIO initialized for notifications with async mode: threading")
    return socketio

def log_all_rooms():
    """Debug function to log all active rooms"""
    global user_sessions
    logger.info(f"Active user sessions: {user_sessions}")
    logger.info(f"SocketIO rooms: {socketio.server.manager.rooms if socketio else 'SocketIO not initialized'}")

def send_auth_notification(username, message, category="info"):
    """
    Send an authentication-related notification to a specific user
    
    Args:
        username: The username to send the notification to
        message: The notification message
        category: The notification category (info, warning, success, error)
    """
    if not socketio:
        logger.warning("SocketIO not initialized, can't send auth notification")
        return False
        
    try:
        logger.info(f"Sending auth notification to {username}: {message}")
        
        # Check if user is in our session mapping
        sid = user_sessions.get(username)
        if not sid:
            logger.warning(f"No active session found for user {username}")
            log_all_rooms()
            
        # Emit to the username room
        socketio.emit('notification', {
            'type': 'auth',
            'category': category,
            'message': message,
            'requires_action': '2FA' in message,
            'timestamp': time.strftime('%H:%M:%S')
        }, room=username)
        
        logger.info(f"Auth notification sent to room '{username}'")
        return True
    except Exception as e:
        logger.error(f"Failed to send auth notification: {str(e)}", exc_info=True)
        return False

def send_course_notification(username, course_code, section, seats_available, total_seats):
    """
    Send a course availability notification to a specific user
    
    Args:
        username: The username to send the notification to
        course_code: The course code (e.g., 'MAT1033')
        section: The section number
        seats_available: Number of available seats
        total_seats: Total number of seats
    """
    if not socketio:
        logger.warning("SocketIO not initialized, can't send course notification")
        return False
        
    try:
        message = f"SEATS AVAILABLE: {course_code}-{section} has {seats_available}/{total_seats} seats open!"
        logger.info(f"Sending course notification to {username}: {message}")
        
        # Check if user is in our session mapping
        sid = user_sessions.get(username)
        if not sid:
            logger.warning(f"No active session found for user {username} for course notification")
            log_all_rooms()
        
        # Emit to the username room
        socketio.emit('notification', {
            'type': 'course_availability',
            'category': 'success',
            'course_code': course_code,
            'section': section, 
            'seats_available': seats_available,
            'total_seats': total_seats,
            'message': message,
            'timestamp': time.strftime('%H:%M:%S')
        }, room=username)
        
        logger.info(f"Course notification sent to room '{username}'")
        return True
    except Exception as e:
        logger.error(f"Failed to send course notification: {str(e)}", exc_info=True)
        return False

def send_global_notification(message, category="info"):
    """Send a notification to all connected clients"""
    if not socketio:
        logger.warning("SocketIO not initialized, can't send global notification")
        return False
        
    try:
        logger.info(f"Sending global notification: {message}")
        socketio.emit('notification', {
            'type': 'system',
            'category': category,
            'message': message,
            'timestamp': time.strftime('%H:%M:%S')
        })
        return True
    except Exception as e:
        logger.error(f"Failed to send global notification: {str(e)}")
        return False

# SocketIO event handlers
def register_socket_events(socketio):
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        sid = request.sid
        logger.info(f"Client connected: {sid}")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection"""
        sid = request.sid
        logger.info(f"Client disconnected: {sid}")
        
        # Remove user from rooms if they were registered
        for username, session_id in list(user_sessions.items()):
            if session_id == sid:
                leave_room(username, sid)
                del user_sessions[username]
                logger.info(f"User {username} unregistered due to disconnect")
    
    @socketio.on('register')
    def handle_register(data):
        """Register a user to receive notifications"""
        sid = request.sid
        if 'username' in data:
            username = data['username']
            
            # Store the mapping of username to sid
            user_sessions[username] = sid
            
            # Join the room with the username
            join_room(username, sid)
            
            logger.info(f"User {username} registered for notifications with sid {sid}")
            
            # Send a test message to confirm registration worked
            socketio.emit('registration_response', {
                'status': 'success',
                'message': f'Successfully registered for notifications as {username}',
                'timestamp': time.strftime('%H:%M:%S')
            }, room=sid)
            
            # Log the rooms this sid is in
            client_rooms = rooms(sid=sid)
            logger.info(f"Rooms for {username} ({sid}): {client_rooms}")
            
            return {'status': 'success', 'message': 'Registered for notifications'}
        return {'status': 'error', 'message': 'Username required'}
    
    @socketio.on('request_test_notification')
    def handle_test_notification(data):
        """Handle client requesting a test notification"""
        sid = request.sid
        username = data.get('username')
        
        if not username:
            for u, s in user_sessions.items():
                if s == sid:
                    username = u
                    break
        
        if username:
            logger.info(f"Test notification requested by {username}")
            
            # Send a test notification through the same channel
            send_auth_notification(
                username, 
                f"This is a test notification. If you're seeing this, notifications are working! (SID: {sid})",
                "success"
            )
            
            # Also send a direct response
            socketio.emit('notification', {
                'type': 'system',
                'category': 'info',
                'message': f"Test notification confirmed. Direct response from server to SID: {sid}",
                'timestamp': time.strftime('%H:%M:%S')
            }, room=sid)
            
            return {'status': 'success', 'message': 'Test notification sent'}
        else:
            logger.warning(f"Test notification requested but no username found for SID {sid}")
            return {'status': 'error', 'message': 'No username found for this session'}

    @socketio.on_error()
    def handle_error(e):
        """Handle SocketIO errors"""
        logger.error(f"SocketIO error: {str(e)}", exc_info=True)
