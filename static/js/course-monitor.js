/**
 * Course monitoring functionality
 * Handles toggle monitoring buttons and related interactions
 */

// For debugging purposes
console.log('course-monitor.js loaded');

// Format time from 24-hour to 12-hour format
function convertTo12HourFormat(time24) {
    if (!time24 || typeof time24 !== 'string') return 'N/A';
    
    try {
        const hours = parseInt(time24.substring(0, 2));
        const minutes = time24.substring(2);
        
        let hours12 = hours % 12;
        if (hours12 === 0) hours12 = 12;
        
        const period = hours >= 12 ? 'PM' : 'AM';
        return `${hours12}:${minutes} ${period}`;
    } catch (err) {
        console.error('Time format error:', err);
        return time24; // Return original if parsing fails
    }
}

// Send monitor toggle request to server
function sendToggleMonitorRequest(buttonElement, courseCode, section, isCurrentlyMonitoring, year, term) {
    // Debug info
    console.log(`Sending toggle request: course=${courseCode}, section=${section}, currentlyMonitoring=${isCurrentlyMonitoring}`);
    
    // Show processing state
    const originalText = buttonElement.textContent;
    buttonElement.textContent = isCurrentlyMonitoring ? "Stopping..." : "Starting...";
    buttonElement.disabled = true;
    
    // Prepare request body
    const requestBody = {
        courseCode: courseCode,
        section: section,
        monitor: !isCurrentlyMonitoring // We want to toggle the current state
    };
    
    // Add year and term only when starting to monitor
    if (!isCurrentlyMonitoring) {
        requestBody.year = year;
        requestBody.term = term;
    }
    
    console.log("Request payload:", JSON.stringify(requestBody));
    
    // Send the request
    fetch('/toggle_monitor', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => {
        console.log("Response received:", response.status);
        
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || `Server error: ${response.status}`);
            });
        }
        
        return response.json();
    })
    .then(data => {
        console.log("Success data:", data);
        
        // Update button appearance based on the new state
        if (isCurrentlyMonitoring) {
            // Now we're not monitoring
            buttonElement.textContent = "Start Monitoring";
            buttonElement.classList.remove("btn-danger");
            buttonElement.classList.add("btn-success");
            buttonElement.dataset.monitoring = "0";
        } else {
            // Now we are monitoring
            buttonElement.textContent = "Stop Monitoring";
            buttonElement.classList.remove("btn-success");
            buttonElement.classList.add("btn-danger");
            buttonElement.dataset.monitoring = "1";
        }
        
        // Show success message
        showAlert(data.message || 'Monitoring status updated successfully', 'success');
    })
    .catch(error => {
        console.error("Error:", error);
        showAlert('Error: ' + error.message, 'danger');
        buttonElement.textContent = originalText; // Restore original text
    })
    .finally(() => {
        buttonElement.disabled = false;
    });
}

// Helper function to show alerts
function showAlert(message, type = 'info', autoDismiss = true) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Find a suitable container for the alert
    const container = document.querySelector('.container');
    if (container) {
        container.prepend(alertDiv);
    } else {
        document.body.prepend(alertDiv);
    }
    
    // Auto-dismiss after 5 seconds if requested
    if (autoDismiss) {
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, 5000);
    }
}

// Initialize the monitoring functionality when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing course monitoring...');
    
    try {
        // Format times in the table
        document.querySelectorAll('.formatted-time').forEach(span => {
            const startTime = span.dataset.startTime;
            const endTime = span.dataset.endTime;
            
            if (startTime && endTime) {
                const formattedStart = convertTo12HourFormat(startTime);
                const formattedEnd = convertTo12HourFormat(endTime);
                span.textContent = `${formattedStart} - ${formattedEnd}`;
            }
        });
        
        // Set up ALL toggle monitoring buttons
        const toggleButtons = document.querySelectorAll('.toggle-monitor-btn');
        console.log(`Found ${toggleButtons.length} toggle buttons on the page`);
        
        if (toggleButtons.length === 0) {
            console.warn('No toggle buttons found! Check your HTML structure and class names.');
        }
        
        // Clear any existing click handlers and set new ones
        toggleButtons.forEach((button, index) => {
            // Log button data
            console.log(`Setting up button ${index+1}:`, button.dataset);
            
            // Remove existing handlers to avoid duplicates
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            
            // Set up fresh click handler
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                console.log(`Button ${index+1} clicked`);
                
                // Get button data
                const courseCode = this.dataset.courseCode;
                const section = this.dataset.section;
                const isMonitoring = this.dataset.monitoring === "1";
                const year = this.dataset.year;
                const term = this.dataset.term;
                
                console.log('Button data:', {
                    courseCode, section, isMonitoring, year, term
                });
                
                // Validate required data
                if (!courseCode || !section) {
                    alert('Error: Missing course information');
                    return;
                }
                
                // For starting monitoring, ensure we have year and term
                if (!isMonitoring) {
                    // Validate year and term
                    if (!year || !term) {
                        alert('Error: Year and term are required to monitor a course');
                        return;
                    }
                    sendToggleMonitorRequest(this, courseCode, section, isMonitoring, year, term);
                } else {
                    // For stopping monitoring
                    sendToggleMonitorRequest(this, courseCode, section, isMonitoring, year, term);
                }
            });
        });
    } catch (err) {
        console.error('Error initializing course monitoring:', err);
        showAlert('Error initializing course monitoring: ' + err.message, 'danger', false);
    }
});
