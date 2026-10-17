/** @odoo-module **/
/**
 * Dojo AI Voice Assistant — floating chat panel for the instructor and admin
 * dashboards.
 *
 * Features
 * --------
 *  • Text input — type and send a message
 *  • Voice input — click the mic button to record, click again to submit
 *  • AI responses via the dojo-scoped /dojo/ai/* endpoints
 *  • Contact-parent action card — AI can propose a draft message; the user
 *    can edit subject / body, toggle email/SMS, and confirm the send
 *  • Optional text-to-speech — browser SpeechSynthesis reads AI responses aloud
 */

import { Component, proxy, signal, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

// ─── helpers ────────────────────────────────────────────────────────────────

function nowLabel() {
    return new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function htmlToPlain(html) {
    if (!html) return "";
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return tmp.textContent || tmp.innerText || "";
}

function formatConfidence(val) {
    if (val === null || val === undefined) return null;
    return Math.round(val * 100) + "%";
}

function formatMs(ms) {
    if (!ms) return null;
    return ms < 1000 ? ms + "ms" : (ms / 1000).toFixed(1) + "s";
}

// Minimal fallback steps shown while waiting when n8n has no step nodes configured.
const FALLBACK_STEPS = [
    { name: "Analyzing request",  detail: "Understanding what you're asking for..." },
    { name: "Routing to agent",   detail: "Finding the right specialist to handle this..." },
    { name: "Querying database",  detail: "Looking up the relevant records..." },
    { name: "Formatting results", detail: "Putting together your response..." },
];


// ─── component ──────────────────────────────────────────────────────────────

export class DojoVoiceAssistant extends Component {
    static template = "ai_assistant.VoiceAssistant";

    setup() {
        this.notification = useService("notification");
        this.inputRef = signal.ref();
        this.endRef = signal.ref();

        this.state = proxy({
            open: false,
            messages: [],          // [{role, text, time}] — grows forever, never cleared
            contextWindow: [],     // [{role, text}] — rolling window sent to LLM; resets on new session
            input: "",
            recording: false,
            processing: false,
            thinkingHint: false,
            ttsEnabled: false,     // auto-speak AI responses
            pendingAction: null,   // contact_parent action dict from AI
            actionSubject: "",
            actionBody: "",
            actionEmail: true,
            actionSms: true,
            // Two-phase confirmation flow
            pendingConfirm: null,  // {session_key, prompt, intent_type}
            pendingClarificationKey: null,  // clarification session key for multi-turn follow-ups
            liveTranscript: "",
            // n8n pipeline steps (shown while processing)
            liveSteps: [],
            liveStepIdx: 0,
        });

        this._mediaRecorder = null;
        this._audioChunks = [];
        this._stream = null;
        this._currentAudio = null;
        this._recordTimeout = null;
        this._speechSupported = ('SpeechRecognition' in window) || ('webkitSpeechRecognition' in window);
        this._recognition = null;
        this._pendingTranscript = "";
        this._silenceTimer = null;
        this._hasBeenOpened = false;  // tracks first open vs reopen
        this._contextWindowMax = 10;     // turns; overwritten by /dojo/ai/config on mount
        this._chatSessionId = null;  // generated per chat session, sent to n8n for memory
        this._userName = "";  // populated from /dojo/ai/config
        // Pipeline step polling (n8n)
        this._pollInterval = null;
        this._fallbackInterval = null;
        this._fallbackTimer = null;
        this._pollHadResults = false;

        onMounted(() => {
            // Keyboard shortcut: Ctrl+Shift+A to toggle panel
            document.addEventListener("keydown", (e) => {
                if (e.ctrlKey && e.shiftKey && e.key === "A") this.toggle();
            });
            // Fetch configurable context window size
            rpc("/dojo/ai/config", {}).then((cfg) => {
                if (cfg && cfg.context_window_turns) {
                    this._contextWindowMax = cfg.context_window_turns;
                }
                if (cfg && cfg.user_first_name) {
                    this._userName = cfg.user_first_name;
                }
            }).catch(() => { /* keep default */ });
        });

        onWillUnmount(() => {
            if (this._currentAudio) { this._currentAudio.pause(); this._currentAudio = null; }
            if (this._recognition) {
                this._recognition.abort();
                this._recognition = null;
            }
            if (this._mediaRecorder && this._mediaRecorder.state !== "inactive") {
                this._mediaRecorder.stop();
            }
            if (this._stream) {
                this._stream.getTracks().forEach(t => t.stop());
                this._stream = null;
            }
            if (this._recordTimeout) {
                clearTimeout(this._recordTimeout);
                this._recordTimeout = null;
            }
            if (this._silenceTimer) {
                clearTimeout(this._silenceTimer);
                this._silenceTimer = null;
            }
        });
    }

    // ── panel open / close ───────────────────────────────────────────────────

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open) {
            if (!this._hasBeenOpened) {
                // Very first open — show welcome
                this._chatSessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
                const name = this._userName || "there";
                this._pushMsg("assistant", `👋 Hi ${name}! I can help you with scheduling, student lookups, or messaging parents. What would you like to do?`);
                this._hasBeenOpened = true;
            } else {
                // Reopen after close — start a new session in this window
                this._chatSessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
                this._pushDivider("── New Session ──");
                this.state.contextWindow = [];
                this.state.pendingClarificationKey = null;
            }
            setTimeout(() => this._scrollToBottom(), 60);
            setTimeout(() => this.inputRef.el && this.inputRef.el.focus(), 80);
        }
    }

    close() { this.state.open = false; }

    // ── messaging ────────────────────────────────────────────────────────────

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    onInputChange(ev) {
        this.state.input = ev.target.value;
    }

    async send() {
        const text = (this.state.input || "").trim();
        if (!text || this.state.processing) return;
        this.state.input = "";
        await this._submitText(text);
    }

    async _submitText(text) {
        this._pushMsg("user", text);
        this.state.processing = true;
        this._scrollToBottom();

        // ── n8n pipeline step tracking ─────────────────────────────────
        const pipelineKey = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2))
            .replace(/-/g, "").slice(0, 12);
        this.state.liveSteps = [{ name: "Processing your request...", detail: "Connecting to AI pipeline..." }];
        this.state.liveStepIdx = 0;
        this._startPoll(pipelineKey);
        this._fallbackTimer = setTimeout(() => {
            if (!this._pollHadResults) this._startFallback();
        }, 12500);

        // Abort controller for timeout + cancel
        this._abortCtrl = new AbortController();
        const timeoutId = setTimeout(() => this._abortCtrl.abort(), 45000);

        // "Still thinking" hint after 8s
        const thinkId = setTimeout(() => {
            if (this.state.processing) {
                this.state.thinkingHint = true;
            }
        }, 8000);

        try {
            const result = await rpc("/dojo/ai/text", {
                text,
                conversation_history: this.state.contextWindow,
                chat_session_id: this._chatSessionId,
                clarification_session_key: this.state.pendingClarificationKey || null,
                pipeline_key: pipelineKey,
            });
            if (result.success) {
                if (result.pipeline_steps && result.pipeline_steps.length > 0) {
                    this.state.liveSteps = result.pipeline_steps;
                    this.state.liveStepIdx = result.pipeline_steps.length - 1;
                }
                this._handleAiResult(result);
                this._updateContextWindow(text, result.response || "");
                // Clear clarification key after any non-clarification response
                if (result.state !== "needs_clarification") {
                    this.state.pendingClarificationKey = null;
                }
            } else {
                this._pushMsg("assistant", "⚠️ " + (result.error || "Unknown error."));
            }
        } catch (err) {
            if (this._abortCtrl && this._abortCtrl.signal.aborted) {
                this._pushMsg("assistant", "⚠️ That query took too long. Try a simpler question or break it into parts.");
            } else {
                this._pushMsg("assistant", "⚠️ Network error — please try again.");
            }
        } finally {
            clearTimeout(timeoutId);
            clearTimeout(thinkId);
            this._stopPoll();
            this._stopFallback();
            this.state.processing = false;
            this.state.thinkingHint = false;
            this.state.liveSteps = [];
            this._abortCtrl = null;
            this._scrollToBottom();
        }
    }

    cancelAiRequest() {
        if (this._abortCtrl) this._abortCtrl.abort();
    }

    // ── n8n pipeline step polling ────────────────────────────────────────────

    stepClass(idx) {
        if (idx < this.state.liveStepIdx) return "o-done";
        if (idx === this.state.liveStepIdx) return "o-active";
        return "o-pending";
    }

    _startPoll(pipelineKey) {
        this._stopPoll();
        this._pollHadResults = false;
        this._pollInterval = setInterval(async () => {
            try {
                const r = await rpc("/dojo/ai/steps", { pipeline_key: pipelineKey });
                if (r && r.steps && r.steps.length > 0) {
                    this._pollHadResults = true;
                    this.state.liveSteps = r.steps;
                    this.state.liveStepIdx = r.steps.length - 1;
                    this._stopFallback();
                }
                if (r && r.done) this._stopPoll();
            } catch (_e) { /* ignore poll errors */ }
        }, 400);
    }

    _startFallback() {
        if (this._fallbackInterval) return;
        this._stopFallbackTimer();
        this.state.liveSteps = [...FALLBACK_STEPS];
        this.state.liveStepIdx = 0;
        let idx = 0;
        const max = FALLBACK_STEPS.length - 1;
        this._fallbackInterval = setInterval(() => {
            if (idx < max) { idx++; this.state.liveStepIdx = idx; }
        }, 900);
    }

    _stopPoll() {
        if (this._pollInterval) { clearInterval(this._pollInterval); this._pollInterval = null; }
    }

    _stopFallback() {
        this._stopFallbackTimer();
        if (this._fallbackInterval) { clearInterval(this._fallbackInterval); this._fallbackInterval = null; }
    }

    _stopFallbackTimer() {
        if (this._fallbackTimer) { clearTimeout(this._fallbackTimer); this._fallbackTimer = null; }
    }

    // ── voice recording ──────────────────────────────────────────────────────

    async toggleRecording() {
        if (this.state.recording) {
            this._stopVoiceInput();
        } else {
            await this._startVoiceInput();
        }
    }

    async _startVoiceInput() {
        if (this._speechSupported) {
            // ── Chrome / Edge path ──
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            this._recognition = new SR();
            this._recognition.continuous = true;
            this._recognition.interimResults = true;
            this._recognition.lang = "en-US";
            this._pendingTranscript = "";
            this.state.liveTranscript = "";
            this.state.recording = true;

            const resetSilenceTimer = () => {
                if (this._silenceTimer) clearTimeout(this._silenceTimer);
                this._silenceTimer = setTimeout(() => {
                    this._silenceTimer = null;
                    if (this._recognition) this._recognition.stop();
                }, 2500);
            };

            this._recognition.onresult = (event) => {
                let full = "";
                for (let i = 0; i < event.results.length; i++) {
                    full += event.results[i][0].transcript;
                }
                this._pendingTranscript = full;
                this.state.liveTranscript = full;
                resetSilenceTimer();
            };

            this._recognition.onerror = (event) => {
                if (this._silenceTimer) { clearTimeout(this._silenceTimer); this._silenceTimer = null; }
                this._pendingTranscript = "";
                this.state.liveTranscript = "";
                this.state.recording = false;
                if (event.error === "not-allowed") {
                    this.notification.add("Microphone access denied.", { type: "warning" });
                } else {
                    this._pushMsg("assistant", "⚠️ Voice recognition failed, please try again.");
                }
                // onend fires after onerror — _pendingTranscript is '' so it will no-op
            };

            this._recognition.onend = () => {
                if (this._silenceTimer) { clearTimeout(this._silenceTimer); this._silenceTimer = null; }
                this.state.recording = false;
                this.state.liveTranscript = "";
                const text = this._pendingTranscript.trim();
                this._pendingTranscript = "";
                if (text) {
                    this._submitVoiceTranscript(text);
                }
            };

            this._recognition.start();
        } else {
            // ── Fallback: MediaRecorder ──
            await this._startRecording();
            this.state.liveTranscript = "Listening…";
        }
    }

    _stopVoiceInput() {
        if (this._speechSupported && this._recognition) {
            this._recognition.stop();
            // onend fires automatically → submits or no-ops
        } else {
            this._stopRecording();
            this.state.liveTranscript = "";
        }
    }

    _submitVoiceTranscript(text) {
        if (this.state.processing) {
            // AI is still responding — put transcript in input so user can submit manually
            this.state.input = text;
            this.state.liveTranscript = "";
            return;
        }
        this.state.liveTranscript = "";
        this._submitText(text);
    }

    async _startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.notification.add("Microphone not available in this browser.", { type: "warning" });
            return;
        }
        try {
            this._stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            this.notification.add("Microphone access denied. Please allow it in your browser.", { type: "warning" });
            return;
        }

        this._audioChunks = [];
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus"
            : "audio/webm";
        this._mediaRecorder = new MediaRecorder(this._stream, { mimeType });

        this._mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) this._audioChunks.push(e.data);
        };
        this._mediaRecorder.onstop = () => this._processRecording();

        this._mediaRecorder.start(250); // collect in 250 ms slices
        this.state.recording = true;

        // Auto-stop after 60 seconds
        this._recordTimeout = setTimeout(() => {
            if (this.state.recording) this._stopRecording();
        }, 60000);
    }

    _stopRecording() {
        if (this._recordTimeout) {
            clearTimeout(this._recordTimeout);
            this._recordTimeout = null;
        }
        if (this._mediaRecorder && this._mediaRecorder.state !== "inactive") {
            this._mediaRecorder.stop();
        }
        if (this._stream) {
            this._stream.getTracks().forEach((t) => t.stop());
            this._stream = null;
        }
        this.state.recording = false;
    }

    async _processRecording() {
        this.state.liveTranscript = "";
        if (!this._audioChunks.length) return;
        const blob = new Blob(this._audioChunks, { type: "audio/webm" });
        this._audioChunks = [];

        this._pushMsg("user", "🎙️ [voice message]");
        this.state.processing = true;
        this._scrollToBottom();

        const pipelineKey = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2))
            .replace(/-/g, "").slice(0, 12);
        this.state.liveSteps = [{ name: "Processing your request...", detail: "Transcribing audio and calling AI pipeline..." }];
        this.state.liveStepIdx = 0;
        this._startPoll(pipelineKey);
        this._fallbackTimer = setTimeout(() => {
            if (!this._pollHadResults) this._startFallback();
        }, 12500);

        const formData = new FormData();
        formData.append("audio", blob, "recording.webm");
        formData.append("conversation_history", JSON.stringify(this.state.contextWindow));
        formData.append("pipeline_key", pipelineKey);

        try {
            const resp = await fetch("/dojo/ai/voice", {
                method: "POST",
                body: formData,
                // Odoo session cookie is sent automatically via the browser
            });
            const result = await resp.json();

            if (result.success) {
                // Replace placeholder with actual transcription
                const msgs = this.state.messages;
                const lastUser = [...msgs].reverse().find((m) => m.role === "user");
                if (lastUser && lastUser.text === "🎙️ [voice message]") {
                    lastUser.text = "🎙️ " + result.transcribed;
                }
                if (result.pipeline_steps && result.pipeline_steps.length > 0) {
                    this.state.liveSteps = result.pipeline_steps;
                    this.state.liveStepIdx = result.pipeline_steps.length - 1;
                }
                this._handleAiResult(result);
                this._updateContextWindow(result.transcribed || "", result.response || "");
            } else {
                this._pushMsg("assistant", "⚠️ " + (result.error || "Voice processing failed."));
            }
        } catch (err) {
            this._pushMsg("assistant", "⚠️ Could not process voice recording.");
        } finally {
            this._stopPoll();
            this._stopFallback();
            this.state.processing = false;
            this.state.liveSteps = [];
            this._scrollToBottom();
        }
    }

    // ── AI result handling ────────────────────────────────────────────────────

    _handleAiResult(result) {
        const text = result.response || "";
        if (text) {
            this._pushMsg("assistant", text);
        } else if (result.state !== "pending_confirmation") {
            this._pushMsg("assistant", "Sorry, I couldn't find an answer for that. Try rephrasing your question.");
        }

        // Speak response if TTS is enabled (ElevenLabs)
        if (this.state.ttsEnabled && text) {
            this._speakResponse(text);
        }

        // ── Clarification follow-up (multi-turn) ─────────────────────────────
        if (result.state === "needs_clarification" && result.session_key) {
            this.state.pendingClarificationKey = result.session_key;
            return;
        }

        // ── Two-phase confirmation (enroll, belt, etc.) ──────────────────────
        if (result.state === "pending_confirmation" && result.session_key && result.confirmation_prompt) {
            this.state.pendingConfirm = {
                session_key: result.session_key,
                prompt: result.confirmation_prompt,
                intent_type: result.intent && result.intent.intent_type,
            };
            if (!text) {
                this._pushMsg("assistant", result.confirmation_prompt);
            }
            return;
        }

        // Handle contact_parent action (legacy)
        const action = result.action;
        if (action && action.type === "contact_parent" && !action.error) {
            this.state.pendingAction = action;
            this.state.actionSubject = action.suggested_subject || "Message from Dojo";
            this.state.actionBody = action.suggested_body || "";
            this.state.actionEmail = true;
            this.state.actionSms = true;
        } else if (action && action.error) {
            this._pushMsg("assistant", "⚠️ " + action.error);
        }
    }

    // ── contact-parent confirmation card ─────────────────────────────────────

    onActionSubjectChange(ev) { this.state.actionSubject = ev.target.value; }
    onActionBodyChange(ev) { this.state.actionBody = ev.target.value; }
    onActionEmailChange(ev) { this.state.actionEmail = ev.target.checked; }
    onActionSmsChange(ev) { this.state.actionSms = ev.target.checked; }

    cancelAction() {
        this.state.pendingAction = null;
        this._pushMsg("assistant", "Message cancelled. Let me know if you need anything else.");
    }

    // ── Two-phase confirmation (enroll / belt / etc.) ─────────────────────────

    async confirmIntent() {
        const pending = this.state.pendingConfirm;
        if (!pending) return;
        this.state.pendingConfirm = null;
        this.state.processing = true;
        try {
            const result = await rpc("/dojo/ai/confirm", {
                session_key: pending.session_key,
                confirmed: true,
            });
            if (result.success) {
                if (result.compound && result.steps && result.steps.length) {
                    const lines = result.steps.map(s => {
                        if (s.skipped) return null;
                        if (s.success) return s.summary || null;
                        return `⚠️ ${s.error || "Step failed"}`;
                    }).filter(Boolean);
                    this._pushMsg("assistant", lines.join("\n\n"));
                } else {
                    const msg = result.result && result.result.message
                        ? "✅ " + result.result.message
                        : "✅ Done!";
                    this._pushMsg("assistant", msg);
                }
                if (result.undo_available) {
                    this._pushMsg("assistant", "You can say \"undo\" to reverse this action.");
                }
            } else {
                if (result.compound && result.steps && result.steps.length) {
                    const lines = result.steps.map(s => {
                        if (s.success) return `✅ ${s.summary || "Completed"}`;
                        return `❌ ${s.error || "Failed"}`;
                    });
                    this._pushMsg("assistant", lines.join("\n\n"));
                } else {
                    this._pushMsg("assistant", "⚠️ " + (result.error || "Action failed."));
                }
            }
        } catch (err) {
            const errMsg = err?.data?.message || err?.message || "Network error during confirmation.";
            this._pushMsg("assistant", "⚠️ " + errMsg);
        } finally {
            this.state.processing = false;
            this._scrollToBottom();
        }
    }

    async cancelIntent() {
        const pending = this.state.pendingConfirm;
        if (!pending) return;
        this.state.pendingConfirm = null;
        try {
            await rpc("/dojo/ai/confirm", {
                session_key: pending.session_key,
                confirmed: false,
            });
        } catch (_) { }
        this._pushMsg("assistant", "Action cancelled. Let me know if you need anything else.");
    }

    async confirmAction() {
        const action = this.state.pendingAction;
        if (!action) return;

        this.state.processing = true;
        try {
            const result = await rpc("/dojo/ai/send_message", {
                member_id: action.member_id,
                subject: this.state.actionSubject,
                body: this.state.actionBody,
                send_email: this.state.actionEmail,
                send_sms: this.state.actionSms,
            });
            this.state.pendingAction = null;
            if (result.success) {
                this._pushMsg("assistant", "✅ " + (result.message || "Message sent successfully."));
                this.notification.add(result.message || "Message sent.", { type: "success" });
            } else {
                this._pushMsg("assistant", "⚠️ Failed to send: " + (result.error || "Unknown error."));
            }
        } catch (err) {
            this._pushMsg("assistant", "⚠️ Network error while sending message.");
        } finally {
            this.state.processing = false;
            this._scrollToBottom();
        }
    }

    // ── TTS toggle ────────────────────────────────────────────────────────────

    toggleTts() {
        this.state.ttsEnabled = !this.state.ttsEnabled;
        if (!this.state.ttsEnabled && this._currentAudio) {
            this._currentAudio.pause();
            this._currentAudio = null;
        }
        this.notification.add(
            this.state.ttsEnabled ? "🔊 Voice responses ON" : "🔇 Voice responses OFF",
            { type: "info", sticky: false }
        );
    }

    async _speakResponse(text) {
        if (!text) return;
        try {
            const result = await rpc("/dojo/ai/speak", { text });
            if (!result || !result.success) {
                this.state.ttsEnabled = false;
                this.notification.add(
                    "🔇 Voice playback unavailable — " + (result && result.error ? result.error : "ElevenLabs TTS failed."),
                    { type: "warning", sticky: true }
                );
                return;
            }
            const audio = new Audio("data:" + result.mime + ";base64," + result.audio_b64);
            if (this._currentAudio) this._currentAudio.pause();
            this._currentAudio = audio;
            audio.onended = () => { this._currentAudio = null; };
            audio.onerror = () => { this._currentAudio = null; };
            audio.play().catch(() => { this._currentAudio = null; });
        } catch (err) {
            this.state.ttsEnabled = false;
            this.notification.add(
                "🔇 Voice playback failed — " + (err.message || "unexpected error"),
                { type: "warning", sticky: true }
            );
        }
    }

    // ── utils ─────────────────────────────────────────────────────────────────

    _pushMsg(role, text) {
        this.state.messages.push({ role, text, time: nowLabel() });
    }
    _pushDivider(text) {
        this.state.messages.push({ role: "divider", text });
    }

    clearContext() {
        this.state.contextWindow = [];
        this._pushDivider("── Context Cleared ──");
        this._scrollToBottom();
    }

    _updateContextWindow(userText, aiText) {
        const cw = this.state.contextWindow;
        if (userText) cw.push({ role: "user", text: userText });
        if (aiText) cw.push({ role: "assistant", text: aiText });
        const maxItems = this._contextWindowMax * 2;  // each turn = user + assistant
        if (cw.length > maxItems) cw.splice(0, cw.length - maxItems);
    }
    _scrollToBottom() {
        if (this.endRef.el) {
            this.endRef.el.scrollIntoView({ behavior: "smooth" });
        }
    }
}
