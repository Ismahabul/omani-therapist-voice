document.addEventListener("DOMContentLoaded", () => {
    const recordBtn = document.getElementById("recordBtn");
    const statusDiv = document.getElementById("status");

    // Check for browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        statusDiv.textContent = "Sorry, your browser doesn't support speech recognition.";
        recordBtn.disabled = true;
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false; // Process after user stops talking
    recognition.lang = 'ar-OM'; // Set to Omani Arabic
    recognition.interimResults = false;

    let isRecording = false;

    recordBtn.addEventListener("click", () => {
        if (isRecording) {
            recognition.stop();
        } else {
            recognition.start();
        }
    });

    recognition.onstart = () => {
        isRecording = true;
        recordBtn.textContent = "Listening...";
        recordBtn.classList.add("recording");
        statusDiv.textContent = "I'm listening...";
    };

    recognition.onend = () => {
        isRecording = false;
        recordBtn.textContent = "Press to Talk";
        recordBtn.classList.remove("recording");
        statusDiv.textContent = "Press the button and start speaking.";
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error", event.error);
        statusDiv.textContent = `Error: ${event.error}`;
    };

    recognition.onresult = async (event) => {
        const userText = event.results[0][0].transcript;
        statusDiv.textContent = `You said: "${userText}"`;
        
        // Send the transcribed text to the backend
        try {
            statusDiv.textContent = "Thinking...";
            const response = await fetch('/process-audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: userText })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();
            const aiReply = data.reply;
            
            // Use the browser's TTS to speak the reply
            speak(aiReply);

        } catch (error) {
            console.error("Error processing audio:", error);
            statusDiv.textContent = "Sorry, I had trouble connecting.";
        }
    };

    function speak(text) {
        const utterance = new SpeechSynthesisUtterance(text);
        
        // IMPORTANT: The browser will likely not have an Omani Arabic voice.
        // It will fall back to a standard Arabic or default system voice.
        // This is a major limitation of the POC.
        utterance.lang = 'ar-SA'; // 'ar-OM' is often not supported, 'ar-SA' is a common fallback
        utterance.rate = 0.9;

        utterance.onstart = () => {
            statusDiv.textContent = "Speaking...";
            recordBtn.disabled = true;
        };

        utterance.onend = () => {
            statusDiv.textContent = "Press the button and start speaking.";
            recordBtn.disabled = false;
        };
        
        window.speechSynthesis.speak(utterance);
    }
});