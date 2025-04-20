/**
 * Simple Sounds - Reliable audio notifications that work across browsers
 */

const SimpleSounds = {
    // Audio context
    audioContext: null,
    initialized: false,
    
    // Initialize the audio system
    init: function() {
        if (this.initialized) return;
        
        try {
            // Try to create AudioContext
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioContext = new AudioContext();
                console.log('Audio context initialized');
                this.initialized = true;
            } else {
                console.warn('Web Audio API not supported in this browser');
            }
        } catch (e) {
            console.error('Failed to initialize audio system:', e);
        }
        
        return this;
    },
    
    // Play a simple beep sound
    beep: function(frequency = 440, duration = 300, volume = 0.1, type = 'sine') {
        if (!this.initialized) this.init();
        if (!this.audioContext) return false;
        
        try {
            const oscillator = this.audioContext.createOscillator();
            const gainNode = this.audioContext.createGain();
            
            oscillator.type = type;
            oscillator.frequency.setValueAtTime(frequency, this.audioContext.currentTime);
            oscillator.connect(gainNode);
            
            gainNode.gain.setValueAtTime(volume, this.audioContext.currentTime);
            gainNode.connect(this.audioContext.destination);
            
            oscillator.start();
            oscillator.stop(this.audioContext.currentTime + duration / 1000);
            
            return true;
        } catch (e) {
            console.error('Error playing sound:', e);
            return false;
        }
    },
    
    // Notification sounds
    notification: function() {
        return this.beep(440, 200, 0.1);
    },
    
    success: function() {
        // Play two ascending tones
        if (!this.initialized) this.init();
        if (!this.audioContext) return false;
        
        this.beep(440, 150, 0.1);
        setTimeout(() => this.beep(523.25, 200, 0.1), 150);
        return true;
    },
    
    alert: function() {
        // Play three quick beeps
        if (!this.initialized) this.init();
        if (!this.audioContext) return false;
        
        this.beep(698.46, 100, 0.15);
        setTimeout(() => this.beep(698.46, 100, 0.15), 150);
        setTimeout(() => this.beep(698.46, 250, 0.15), 300);
        return true;
    },
    
    error: function() {
        // Play descending tones
        if (!this.initialized) this.init();
        if (!this.audioContext) return false;
        
        this.beep(440, 200, 0.2);
        setTimeout(() => this.beep(349.23, 400, 0.2), 200);
        return true;
    },
    
    // Test all sounds
    test: function() {
        console.log('Testing sounds...');
        this.notification();
        setTimeout(() => this.success(), 700);
        setTimeout(() => this.alert(), 1400);
        setTimeout(() => this.error(), 2100);
    }
};

// Initialize on first user interaction
document.addEventListener('click', function initAudio() {
    SimpleSounds.init();
    document.removeEventListener('click', initAudio);
}, { once: true });

// Export to global scope
window.SimpleSounds = SimpleSounds;
