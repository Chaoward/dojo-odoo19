/** @odoo-module **/
/**
 * Dojo AI Voice Assistant — Full-page client action widget.
 *
 * Uses elevenlabs_connector for STT (via /dojo/ai/voice endpoint which
 * internally calls elevenlabs.service.transcribe_audio), but routes all
 * AI processing through the ai_assistant intent engine.
 *
 * Endpoints:
 *   POST /dojo/ai/voice   — multipart audio → elevenlabs STT → dojo AI
 *   POST /dojo/ai/text    — jsonrpc text → dojo AI
 *   POST /dojo/ai/confirm — jsonrpc confirm/reject pending action
 *   POST /dojo/ai/history — jsonrpc recent action log
 */

import { Component, proxy, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

// Fallback steps shown while waiting when n8n has no step nodes configured.
const FALLBACK_STEPS = [
    { name: "Analyzing request",  detail: "Understanding what you're asking for..." },
    { name: "Routing to agent",   detail: "Finding the right specialist to handle this..." },
    { name: "Querying database",  detail: "Looking up the relevant records..." },
    { name: "Formatting results", detail: "Putting together your response..." },
];

class DojoVoiceAssistantPage extends Component {
    static template = "ai_assistant.VoiceAssistantPage";

    setup() {
        this.notification = useService("notification");
        this.state = proxy({
            mode: "voice",              // "voice" | "text"
            isRecording: false,
            isProcessing: false,
            ttsEnabled: false,
            isSpeaking: false,
            textInput: "",
            transcribedText: "",
            aiResponse: "",
            // Confirmation flow
            awaitingConfirmation: false,
            confirmationPrompt: "",
            sessionKey: null,
            undoAvailable: false,
            error: null,
            history: [],
            historyPage: 0,
            historyTotal: 0,
            historyPerPage: 10,
            // Rolling context window sent to LLM; reset when user clicks Clear Context
            contextWindow: [],
            // Clarification follow-up
            pendingClarificationKey: null,
            // n8n pipeline step progress
            liveSteps: [],
            liveStepIdx: 0,
        });

        this._mediaRecorder = null;
        this._audioChunks = [];
        this._currentAudio = null;
        this._chatSessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
        // Pipeline step polling (n8n)
        this._pollInterval = null;
        this._fallbackInterval = null;
        this._fallbackTimer = null;
        this._pollHadResults = false;

        onWillStart(async () => {
            await this.loadHistory();
        });
    }

    // ── History (ai_assistant action log) ───────────────────────────────

    async loadHistory() {
        const offset = this.state.historyPage * this.state.historyPerPage;
        try {
            const result = await rpc("/dojo/ai/history", {
                limit: this.state.historyPerPage,
                offset,
                user_only: true,
            });
            if (result && result.success) {
                this.state.history = (result.records || []).map(r => ({
                    ...r,
                    _badge: this._statusBadge(r),
                    _intent: this._formatIntent(r.intent_type),
                    _time: this._formatTime(r.timestamp),
                }));
                this.state.historyTotal = result.total || 0;
            }
        } catch (e) {
            console.warn("[DojoAI] Failed to load history:", e);
        }
    }

    get historyTotalPages() {
        return Math.max(1, Math.ceil(this.state.historyTotal / this.state.historyPerPage));
    }

    get hasNextPage() {
        return this.state.historyPage < this.historyTotalPages - 1;
    }

    get hasPrevPage() {
        return this.state.historyPage > 0;
    }

    async prevPage() {
        if (this.hasPrevPage) {
            this.state.historyPage--;
            await this.loadHistory();
        }
    }

    async nextPage() {
        if (this.hasNextPage) {
            this.state.historyPage++;
            await this.loadHistory();
        }
    }

    // ── Recording (same MediaRecorder approach) ──────────────────────────

    async toggleRecording() {
        if (this.state.isRecording) {
            this._stopRecording();
        } else {
            await this._startRecording();
        }
    }

    async _startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.state.error = "Microphone is not supported in this browser.";
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this._audioChunks = [];

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm")
                    ? "audio/webm"
                    : "";

            this._mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

            this._mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) this._audioChunks.push(e.data);
            };

            this._mediaRecorder.onstop = () => {
                const blob = new Blob(this._audioChunks, { type: mimeType || "audio/webm" });
                stream.getTracks().forEach(t => t.stop());
                this._processAudio(blob);
            };

            this._mediaRecorder.start();
            this.state.isRecording = true;
            this.state.error = null;
            this._clearResult();
        } catch (e) {
            this.state.error = "Could not access microphone. Please check permissions.";
        }
    }

    _stopRecording() {
        if (this._mediaRecorder && this.state.isRecording) {
            this._mediaRecorder.stop();
            this.state.isRecording = false;
        }
    }

    // ── Audio → /dojo/ai/voice (multipart, elevenlabs STT → dojo AI) ────

    async _processAudio(blob) {
        this.state.isProcessing = true;
        this.state.error = null;
        this.state.transcribedText = "";
        this.state.aiResponse = "";

        const pipelineKey = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2))
            .replace(/-/g, "").slice(0, 12);
        this.state.liveSteps = [{ name: "Processing audio...", detail: "Transcribing and routing to AI pipeline..." }];
        this.state.liveStepIdx = 0;
        this._startPoll(pipelineKey);
        this._fallbackTimer = setTimeout(() => {
            if (!this._pollHadResults) this._startFallback();
        }, 12500);

        try {
            const formData = new FormData();
            formData.append("audio", blob, "voice.webm");
            formData.append("conversation_history", JSON.stringify(this.state.contextWindow));
            formData.append("chat_session_id", this._chatSessionId);
            formData.append("pipeline_key", pipelineKey);

            const resp = await fetch("/dojo/ai/voice", {
                method: "POST",
                body: formData,
                credentials: "same-origin",
            });

            let result;
            try { result = await resp.json(); } catch (_) {}
            if (!resp.ok || !result) {
                const msg = result && result.error ? result.error : `Server error ${resp.status}`;
                throw new Error(msg);
            }
            this._handleResult(result, null);
        } catch (e) {
            this.state.error = e.message || "Failed to process audio. Please try again.";
            console.error("[DojoAI] Audio error:", e);
        } finally {
            this._stopPoll();
            this._stopFallback();
            this.state.liveSteps = [];
            this.state.isProcessing = false;
        }
    }

    // ── Text mode ────────────────────────────────────────────────────────

    async submitText() {
        const text = (this.state.textInput || "").trim();
        if (!text || this.state.isProcessing) return;

        this.state.isProcessing = true;
        this.state.error = null;
        this.state.aiResponse = "";
        this.state.awaitingConfirmation = false;
        const entered = text;
        this.state.textInput = "";

        const pipelineKey = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2))
            .replace(/-/g, "").slice(0, 12);
        this.state.liveSteps = [{ name: "Processing your request...", detail: "Connecting to AI pipeline..." }];
        this.state.liveStepIdx = 0;
        this._startPoll(pipelineKey);
        this._fallbackTimer = setTimeout(() => {
            if (!this._pollHadResults) this._startFallback();
        }, 12500);

        try {
            const result = await rpc("/dojo/ai/text", {
                text: entered,
                conversation_history: this.state.contextWindow,
                chat_session_id: this._chatSessionId,
                clarification_session_key: this.state.pendingClarificationKey || null,
                pipeline_key: pipelineKey,
            });
            this._handleResult(result, entered);
        } catch (e) {
            this.state.error = "Failed to process command. Please try again.";
            console.error("[DojoAI] Text error:", e);
        } finally {
            this._stopPoll();
            this._stopFallback();
            this.state.liveSteps = [];
            this.state.isProcessing = false;
        }
    }

    onTextKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.submitText();
        }
    }

    // ── Result handling (supports two-phase confirmation) ────────────────

    _handleResult(result, fallbackText) {
        if (!result || !result.success) {
            this.state.error = (result && result.error) || "An unexpected error occurred.";
            return;
        }

        this.state.transcribedText = result.transcribed || fallbackText || "";

        if (result.state === "pending_confirmation") {
            this.state.awaitingConfirmation = true;
            this.state.sessionKey = result.session_key || null;
            this.state.confirmationPrompt = result.confirmation_prompt || result.response || "Please confirm this action.";
            this.state.aiResponse = "";
            this.state.pendingClarificationKey = null;
            this._speakResponse(this.state.confirmationPrompt);
        } else if (result.state === "needs_clarification") {
            this.state.awaitingConfirmation = false;
            this.state.sessionKey = null;
            this.state.aiResponse = result.response || "Could you clarify?";
            if (result.session_key) {
                this.state.pendingClarificationKey = result.session_key;
            }
            this._speakResponse(this.state.aiResponse);
            // Update context so follow-up has history
            const userText = this.state.transcribedText || fallbackText || "";
            if (userText) this.state.contextWindow.push({ role: "user", text: userText });
            if (this.state.aiResponse) this.state.contextWindow.push({ role: "assistant", text: this.state.aiResponse });
            if (this.state.contextWindow.length > 20) this.state.contextWindow.splice(0, this.state.contextWindow.length - 20);
        } else if (result.state === "executed") {
            this.state.awaitingConfirmation = false;
            this.state.sessionKey = null;
            this.state.aiResponse = result.response || "Done!";
            this.state.undoAvailable = !!result.undo_available;
            this._speakResponse(this.state.aiResponse);
            // Update rolling context window
            const userText = this.state.transcribedText || fallbackText || "";
            if (userText) this.state.contextWindow.push({ role: "user", text: userText });
            if (this.state.aiResponse) this.state.contextWindow.push({ role: "assistant", text: this.state.aiResponse });
            if (this.state.contextWindow.length > 20) this.state.contextWindow.splice(0, this.state.contextWindow.length - 20);
            this.loadHistory();
        } else if (result.state === "error") {
            this.state.error = result.error || "An error occurred.";
        }
    }

    toggleTts() {
        this.state.ttsEnabled = !this.state.ttsEnabled;
        if (!this.state.ttsEnabled && this._currentAudio) {
            this._currentAudio.pause();
            this._currentAudio = null;
            this.state.isSpeaking = false;
        }
    }

    async _speakResponse(text) {
        if (!this.state.ttsEnabled || !text) return;
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
            if (this._currentAudio) {
                this._currentAudio.pause();
            }
            this._currentAudio = audio;
            this.state.isSpeaking = true;
            audio.onended = () => { this.state.isSpeaking = false; this._currentAudio = null; };
            audio.onerror = () => { this.state.isSpeaking = false; this._currentAudio = null; };
            audio.play().catch(() => { this.state.isSpeaking = false; this._currentAudio = null; });
        } catch (err) {
            this.state.isSpeaking = false;
            this.state.ttsEnabled = false;
            this.notification.add(
                "🔇 Voice playback failed — " + (err.message || "unexpected error"),
                { type: "warning", sticky: true }
            );
        }
    }

    // ── Confirm / Cancel ─────────────────────────────────────────────────

    async confirmAction() {
        await this._doConfirm(true);
    }

    async cancelAction() {
        await this._doConfirm(false);
    }

    async _doConfirm(confirmed) {
        if (!this.state.sessionKey || this.state.isProcessing) return;
        this.state.isProcessing = true;

        try {
            const result = await rpc("/dojo/ai/confirm", {
                session_key: this.state.sessionKey,
                confirmed,
            });

            this.state.awaitingConfirmation = false;
            this.state.sessionKey = null;

            if (!result || !result.success) {
                this.state.error = (result && result.error) || "Failed to process action.";
                return;
            }

            if (!confirmed) {
                this.state.aiResponse = "Action cancelled.";
            } else {
                const r = result.result || {};
                this.state.aiResponse = result.response || r.response || r.message || "Action completed!";
                this.state.undoAvailable = !!result.undo_available;
            }
            this.loadHistory();
        } catch (e) {
            this.state.error = "Failed to confirm action. Please try again.";
        } finally {
            this.state.isProcessing = false;
        }
    }

    // ── Undo ─────────────────────────────────────────────────────────────

    async requestUndo() {
        this.state.isProcessing = true;
        try {
            const result = await rpc("/dojo/ai/undo", {});
            if (result && result.success) {
                this.state.awaitingConfirmation = true;
                this.state.sessionKey = result.session_key;
                this.state.confirmationPrompt = result.confirmation_prompt || "Undo the last action?";
                this.state.aiResponse = "";
                this.state.undoAvailable = false;
            } else {
                this.state.error = (result && result.error) || "Nothing to undo.";
            }
        } catch (e) {
            this.state.error = "Undo request failed.";
        } finally {
            this.state.isProcessing = false;
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────

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
            } catch (_e) { /* ignore */ }
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

    _clearResult() {
        this.state.aiResponse = "";
        this.state.transcribedText = "";
        this.state.awaitingConfirmation = false;
        this.state.sessionKey = null;
        this.state.error = null;
        this.state.undoAvailable = false;
        this.state.confirmationPrompt = "";
    }

    clearConversation() {
        this._clearResult();
    }

    clearContext() {
        this.state.contextWindow = [];
        this.notification.add("Context cleared — the AI will start fresh on your next message.", { type: "info", sticky: false });
    }

    setMode(mode) {
        if (mode !== this.state.mode) {
            if (this.state.isRecording) this._stopRecording();
            this._clearResult();
            this.state.mode = mode;
        }
    }

    _statusBadge(rec) {
        if (rec.undone) return { text: "Undone", cls: "badge text-bg-secondary" };
        if (rec.execution_status === "error") return { text: "Error", cls: "badge text-bg-danger" };
        if (rec.confirmation_status === "rejected") return { text: "Cancelled", cls: "badge text-bg-warning" };
        if (rec.execution_status === "success") return { text: "Done", cls: "badge text-bg-success" };
        if (rec.confirmation_status === "pending") return { text: "Pending", cls: "badge text-bg-info" };
        return { text: rec.confirmation_status || "—", cls: "badge text-bg-secondary" };
    }

    _formatIntent(type) {
        if (!type) return "";
        return type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    _formatTime(iso) {
        if (!iso) return "";
        try {
            return new Date(iso).toLocaleString([], {
                month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
            });
        } catch { return iso; }
    }
}

registry.category("actions").add("ai_assistant.voice_assistant_page", DojoVoiceAssistantPage);
