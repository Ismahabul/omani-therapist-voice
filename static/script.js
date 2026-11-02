document.addEventListener("DOMContentLoaded", () => {
    const recordBtn = document.getElementById("recordBtn");
    const statusDiv = document.getElementById("status");
    const resetBtn = document.getElementById("resetBtn");
    const crisisNotice = document.getElementById("crisisNotice");

    // Persistent or ephemeral session id per tab
    let sessionId = sessionStorage.getItem("elile_session_id");
    if (!sessionId) {
        sessionId = "session_" + Math.random().toString(36).substring(2, 10);
        sessionStorage.setItem("elile_session_id", sessionId);
    }

    // Check for browser Speech Recognition support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        statusDiv.textContent = "عذراً، متصفحك لا يدعم خاصية التعرف على الصوت (Web Speech API). يرجى استخدام متصفح حديث مثل Chrome أو Edge.";
        recordBtn.disabled = true;
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'ar-OM'; // Prioritize Omani Arabic
    recognition.interimResults = false;

    let isRecording = false;

    // Cache voices when loaded
    let cachedVoices = [];
    if ('speechSynthesis' in window) {
        cachedVoices = window.speechSynthesis.getVoices();
        window.speechSynthesis.onvoiceschanged = () => {
            cachedVoices = window.speechSynthesis.getVoices();
        };
    }

    recordBtn.addEventListener("click", () => {
        if (isRecording) {
            recognition.stop();
        } else {
            // Cancel any ongoing speech when user starts talking
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
            }
            try {
                recognition.start();
            } catch (err) {
                console.warn("Recognition already started:", err);
            }
        }
    });

    if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
            }
            try {
                await fetch('/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                });
                statusDiv.textContent = "تم بدء جلسة جديدة. تفضل بالحديث...";
                if (crisisNotice) crisisNotice.style.display = "none";
            } catch (err) {
                console.error("Failed to reset session:", err);
            }
        });
    }

    recognition.onstart = () => {
        isRecording = true;
        recordBtn.innerHTML = "<span>أستمع إليك...</span>";
        recordBtn.classList.add("recording");
        statusDiv.textContent = "أنا أستمع إليك الآن... تفضل";
    };

    recognition.onend = () => {
        isRecording = false;
        recordBtn.innerHTML = "<span>اضغط وتكلم</span>";
        recordBtn.classList.remove("recording");
    };

    recognition.onerror = (event) => {
        isRecording = false;
        recordBtn.classList.remove("recording");
        recordBtn.disabled = false;
        console.error("Speech recognition error:", event.error);
        if (event.error === 'no-speech') {
            statusDiv.textContent = "لم أسمع شيئاً. اضغط على الزر مرة ثانية وحاول التحدث.";
        } else if (event.error === 'not-allowed') {
            statusDiv.textContent = "يرجى السماح بصلاحية الميكروفون لتتمكن من التحدث.";
        } else {
            statusDiv.textContent = `حدث تنبيه: ${event.error}. حاول مرة ثانية.`;
        }
    };

    recognition.onresult = async (event) => {
        const userText = event.results[0][0].transcript;
        statusDiv.textContent = `أنت قلت: "${userText}"`;
        
        // Disable button while processing backend response
        recordBtn.disabled = true;
        statusDiv.textContent = "جاري التفكير والتجهيز للرد...";

        try {
            const response = await fetch('/process-audio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: userText,
                    session_id: sessionId
                })
            });

            if (!response.ok) {
                throw new Error(`Server returned HTTP ${response.status}`);
            }

            const data = await response.json();
            const aiReply = data.reply;

            if (data.is_crisis && crisisNotice) {
                crisisNotice.style.display = "block";
            }

            // Synthesize voice
            speak(aiReply);

        } catch (error) {
            console.error("Error communicating with server:", error);
            statusDiv.textContent = "عذراً، حدث خطأ أثناء الاتصال بالخادم. يرجى المحاولة بعد قليل.";
            recordBtn.disabled = false;
        }
    };

    function speak(text) {
        if (!('speechSynthesis' in window)) {
            statusDiv.textContent = text;
            recordBtn.disabled = false;
            return;
        }

        // Cancel any pending speech
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'ar-SA'; // Standard Arabic fallback
        utterance.rate = 0.95;

        // Try to locate best matching Arabic voice
        const arabicVoice = cachedVoices.find(v => v.lang === 'ar-OM') || 
                            cachedVoices.find(v => v.lang.startsWith('ar'));
        if (arabicVoice) {
            utterance.voice = arabicVoice;
        }

        utterance.onstart = () => {
            statusDiv.textContent = text;
            recordBtn.disabled = true;
        };

        utterance.onend = () => {
            recordBtn.disabled = false;
            recordBtn.innerHTML = "<span>اضغط وتكلم</span>";
        };

        utterance.onerror = (e) => {
            console.error("SpeechSynthesis error:", e);
            recordBtn.disabled = false;
        };

        window.speechSynthesis.speak(utterance);
    }
});
