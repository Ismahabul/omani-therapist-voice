# OMANI-Therapist-Voice 🇴🇲

**A Proof-of-Concept for a Voice-Only, Culturally-Aware Mental Health AI Companion for the Omani Arabic Dialect.**

This project is a technical assessment and proof-of-concept (POC) that demonstrates the core architecture for building a real-time, voice-first conversational AI focused on mental health support. It is specifically designed to address the unique linguistic and cultural needs of Oman, using the Omani Arabic dialect and incorporating cultural sensitivities.

**Disclaimer:** *This is a proof-of-concept and **not a medical device or a substitute for a licensed therapist**. It demonstrates technical feasibility but lacks the clinical validation, safety hardening, and specialized AI models required for a production system.*

## Table of Contents
- [Project Overview](#project-overview)
- [Core Features](#core-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Running with Docker (Recommended)](#running-with-docker-recommended)
  - [Running Locally (for Development)](#running-locally-for-development)
- [Usage](#usage)
- [Key Project Documents](#key-project-documents)
- [Future Roadmap & Limitations](#future-roadmap--limitations)

## Project Overview

The goal is to build an AI that can provide empathetic, therapeutic-grade conversations exclusively through voice. This POC tackles the foundational challenges of such a system:

- **Real-Time Speech Pipeline:** Capturing user audio, transcribing it, generating a thoughtful response, and synthesizing it back into speech with low latency.
- **Dialect & Culture:** The system is prompted to understand and respond in authentic Omani Arabic, respecting Islamic values, family dynamics, and social norms.
- **Therapeutic Modalities:** The AI's personality is shaped to use principles of Active Listening and Cognitive Behavioral Therapy (CBT).
- **Safety First:** A basic crisis detection mechanism is included to identify high-risk user input and provide an emergency referral.

## Core Features (in this POC)

- **Voice-First Interface:** A simple web UI where users can press a button to talk.
- **Speech-to-Text (STT):** Uses the browser's `SpeechRecognition` API to transcribe user speech (set to `ar-OM`).
- **Intelligent Response Generation:** Leverages OpenAI's `gpt-4o` for its speed, reasoning, and conversational capabilities.
- **Text-to-Speech (TTS):** Uses the browser's `SpeechSynthesis` API to voice the AI's response.
- **Safety Protocol:** A rudimentary keyword-based system to detect crisis situations.
- **Asynchronous Backend:** Built with FastAPI for high-performance I/O operations.
- **Containerized:** Fully containerized with Docker for easy deployment and scalability.

## Architecture

The application follows a simple but powerful client-server model designed for real-time interaction.

```
+----------------+      +---------------------+      +------------------------+
|   User Browser |----->|   FastAPI Backend   |----->|   OpenAI API (GPT-4o)  |
| (STT & TTS)    |      | (Logic & Safety)    |      | (Response Generation)  |
+----------------+      +---------------------+      +------------------------+
        ^                       |
        |                       |
        +-----------------------+
            (Text Response)
```
1.  **Client (Browser):** Captures audio and performs STT. Sends the resulting text to the backend.
2.  **Backend (FastAPI):**
    - Receives the text.
    - Performs a safety check for crisis keywords.
    - Appends the message to the conversation history.
    - Sends the full context to the OpenAI API.
    - Receives the generated text response from OpenAI.
3.  **Client (Browser):** Receives the text response and uses the browser's TTS engine to speak it aloud.

## Tech Stack

- **Backend:** Python 3.11, FastAPI
- **AI Model:** OpenAI GPT-4o
- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Containerization:** Docker
- **Server:** Uvicorn

## Getting Started

You can run this project using Docker (the easiest and recommended way) or locally on your machine for development.

### Prerequisites

- [Docker](https://www.docker.com/get-started) installed on your machine.
- An **OpenAI API Key**. You can get one from the [OpenAI Platform](https://platform.openai.com/).

### Running with Docker (Recommended)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/omani-therapist-voice.git
    cd omani-therapist-voice
    ```

2.  **Build the Docker image:**
    ```bash
    docker build -t omani-therapist-voice .
    ```

3.  **Run the Docker container:**
    Replace `"your_actual_openai_api_key_here"` with your real key.
    ```bash
    docker run -d -p 8000:8000 -e OPENAI_API_KEY="your_actual_openai_api_key_here" --name therapist-app omani-therapist-voice
    ```

4.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.

### Running Locally (for Development)

1.  **Clone the repository and navigate into it.**

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file:**
    Create a file named `.env` in the root of the project and add your API key:
    ```
    OPENAI_API_KEY="your_actual_openai_api_key_here"
    ```

5.  **Run the FastAPI server:**
    ```bash
    uvicorn app:app --reload
    ```

6.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.

## Usage

1.  Open the web application in a compatible browser (like Chrome or Edge).
2.  The browser will ask for microphone permissions. Click **Allow**.
3.  Press the "Press to Talk" button. It will turn blue and say "Listening...".
4.  Speak a phrase in Arabic.
5.  Stop speaking. The app will process your speech and send it to the backend.
6.  The status will change to "Thinking..." and then "Speaking..." as the AI generates and voices its response.

## Key Project Documents

For a deeper understanding of the project's design and future direction, please see:

-   `CULTURAL_ADAPTATION_GUIDE.md`: Details on implementing Omani cultural sensitivity.
-   `SAFETY_PROTOCOL_DOCUMENTATION.md`: A guide to the crisis intervention and safety procedures.
-   `FUTURE_ROADMAP.md`: The path from this POC to a production-ready clinical system.

## Future Roadmap & Limitations

This POC intentionally simplifies many complex components. A production-ready version would require significant investment in the following areas:

-   **Specialized Omani STT/TTS:** The biggest hurdle. A production system needs custom-trained Speech-to-Text and Text-to-Speech models for the Omani dialect to ensure accuracy and a natural-sounding voice. The current browser-based tools are a significant limitation.
-   **Clinical & Safety Hardening:** The safety layer must be expanded beyond keywords to a dedicated, fine-tuned classification model. All protocols must be developed and validated with Omani mental health professionals.
-   **HIPAA-Compliant Infrastructure:** All user data must be handled in a secure, encrypted, and compliant environment.
-   **Dual-Model Strategy:** Implement the fallback logic to query a second model (e.g., Claude 3 Opus) if the primary model fails or gives a low-quality response.
-   **Human-in-the-Loop:** Integrate pathways for professional human supervision and intervention.