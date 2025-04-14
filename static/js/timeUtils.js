/**
 * Time formatting utilities for consistent time display across the application
 */

// Format time in HHMM format (like "0945") to 12-hour format (like "9:45 AM")
function formatTime(time) {
    if (!time || typeof time !== 'string') return 'Time TBA';
    
    // Handle various time formats
    let hours, minutes;
    
    // Try to parse the time string
    if (time.length === 4) {
        // Standard HHMM format
        hours = parseInt(time.substring(0, 2));
        minutes = time.substring(2);
    } else if (time.length === 3) {
        // Possible format like "945" (9:45)
        hours = parseInt(time.substring(0, 1));
        minutes = time.substring(1);
    } else {
        return 'Invalid Time';
    }
    
    // Check if hours and minutes are valid
    if (isNaN(hours) || hours < 0 || hours > 23) {
        return 'Invalid Time';
    }
    
    // Determine AM/PM
    const period = hours >= 12 ? 'PM' : 'AM';
    
    // Convert to 12-hour format
    let hours12 = hours % 12;
    if (hours12 === 0) hours12 = 12; // Handle midnight/noon
    
    // Ensure minutes has leading zeros if needed
    if (minutes.length === 1) minutes = '0' + minutes;
    
    // Return formatted time
    return `${hours12}:${minutes} ${period}`;
}

// Format a time range from HHMM to readable format (e.g., "0900-1030" to "9:00 AM - 10:30 AM")
function formatTimeRange(startTime, endTime) {
    if (!startTime || !endTime) return 'Time TBA';
    return `${formatTime(startTime)} - ${formatTime(endTime)}`;
}

// Parse all time elements on the page when this script is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Find all elements with data-start-time and data-end-time attributes
    const timeElements = document.querySelectorAll('[data-start-time][data-end-time]');
    
    timeElements.forEach(element => {
        const startTime = element.getAttribute('data-start-time');
        const endTime = element.getAttribute('data-end-time');
        
        if (startTime && endTime) {
            element.textContent = formatTimeRange(startTime, endTime);
        }
    });
});
