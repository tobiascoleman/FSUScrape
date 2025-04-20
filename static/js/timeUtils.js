/**
 * Time utilities for FSU Course Scraper
 * Provides consistent time format handling across the application
 */

// Convert time string to minutes since midnight
function timeToMinutes(time) {
    if (!time) return 0;
    
    // Convert to string and ensure it's trimmed
    time = String(time).trim();
    
    let hours, minutes;
    
    // Handle 3-digit format (e.g., "945" for 9:45 AM)
    if (time.length === 3) {
        hours = parseInt(time.substring(0, 1));
        minutes = parseInt(time.substring(1));
    }
    // Handle 4-digit format (e.g., "0945" or "1430")
    else if (time.length === 4) {
        hours = parseInt(time.substring(0, 2));
        minutes = parseInt(time.substring(2));
    }
    else {
        console.warn(`Invalid time format: ${time}`);
        return 0;
    }
    
    return hours * 60 + minutes;
}

// Format time string for display
function formatTime(timeStr) {
    if (!timeStr) return 'TBA';
    
    // Convert to string and ensure it's trimmed
    timeStr = String(timeStr).trim();
    
    let hours, minutes;
    
    // Handle 3-digit format
    if (timeStr.length === 3) {
        hours = parseInt(timeStr.substring(0, 1));
        minutes = timeStr.substring(1);
    }
    // Handle 4-digit format
    else if (timeStr.length === 4) {
        hours = parseInt(timeStr.substring(0, 2));
        minutes = timeStr.substring(2);
    }
    else {
        return timeStr; // Return as is if invalid
    }
    
    // Format minutes to ensure it's always two digits
    if (minutes.length === 1) {
        minutes = '0' + minutes;
    }
    
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12; // Convert 0 to 12
    
    return `${hours}:${minutes} ${ampm}`;
}

// Format time range for display
function formatTimeRange(startTime, endTime) {
    if (!startTime || !endTime) return 'TBA';
    return `${formatTime(startTime)} - ${formatTime(endTime)}`;
}

// Parse FSU's day codes to a standardized format
function parseDays(daysStr) {
    if (!daysStr) return [];
    
    const result = [];
    const dayMap = {
        'M': 'M', // Monday
        'T': 'T', // Tuesday
        'W': 'W', // Wednesday
        'R': 'R', // Thursday (standard format)
        'F': 'F'  // Friday
    };
    
    // Check for TH pattern (special case for Thursday)
    let i = 0;
    while (i < daysStr.length) {
        if (i + 1 < daysStr.length && daysStr[i] === 'T' && 
            (daysStr[i+1] === 'h' || daysStr[i+1] === 'H')) {
            // This is "Th" for Thursday
            result.push('R');  // R is our standardized code for Thursday
            i += 2; // Skip both characters
        } else {
            // Normal single character day
            const day = daysStr[i].toUpperCase();
            if (dayMap[day]) {
                result.push(dayMap[day]);
            }
            i++;
        }
    }
    
    return result;
}

// Detect time conflicts between courses
function hasTimeConflict(course1, course2) {
    // Skip courses without timing info
    if (!course1.days || !course1.startTime || !course1.endTime || 
        !course2.days || !course2.startTime || !course2.endTime) {
        return false;
    }
    
    // Check for day overlap
    const days1 = parseDays(course1.days);
    const days2 = parseDays(course2.days);
    
    const dayOverlap = days1.some(day => days2.includes(day));
    if (!dayOverlap) return false;
    
    // Check time overlap
    const start1 = timeToMinutes(course1.startTime);
    const end1 = timeToMinutes(course1.endTime);
    const start2 = timeToMinutes(course2.startTime);
    const end2 = timeToMinutes(course2.endTime);
    
    return Math.max(start1, start2) < Math.min(end1, end2);
}

// Calculate course duration in minutes
function calculateDuration(startTime, endTime) {
    if (!startTime || !endTime) return 0;
    
    const startMinutes = timeToMinutes(startTime);
    const endMinutes = timeToMinutes(endTime);
    
    return Math.max(0, endMinutes - startMinutes);
}

// Export functions to global scope
window.TimeUtils = {
    timeToMinutes,
    formatTime,
    formatTimeRange,
    parseDays,
    hasTimeConflict,
    calculateDuration
};
