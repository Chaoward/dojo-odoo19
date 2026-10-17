/** @odoo-module **/
/**
 * crm_convert_stripe_payment.js  (dojo_crm)
 * ──────────────────────────────────────────
 * OWL widget that embeds a Stripe PaymentElement inside the CRM Convert wizard.
 * Adapted from dojo_onboarding_stripe's OnboardingStripePayment widget.
 */

import { registry } from "@web/core/registry";
import { Component, proxy, onMounted, signal, useEffect } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

class CrmConvertStripePayment extends Component {
    static template = "dojo_crm.CrmConvertStripePayment";

    static props = {
        record: { type: Object },
        readonly: { type: Boolean, optional: true },
    };

    setup() {
        this.state = proxy({
            status: "idle",
            errorMessage: "",
            cardDisplay: "",
        });
        this.mountRef = signal.ref();
        this.stripe = null;
        this.elements = null;
        this._pendingPaymentEl = null;

        useEffect(
            (status) => {
                if (status === "ready" && this._pendingPaymentEl && this.mountRef.el) {
                    this._pendingPaymentEl.mount(this.mountRef.el);
                    this._pendingPaymentEl = null;
                }
            },
            () => [this.state.status],
        );

        onMounted(() => {
            const data = this.props.record.data;
            if (data.payment_captured) {
                this.state.status = "done";
                this.state.cardDisplay = data.stripe_card_display || "Card saved";
            } else {
                // Don't auto-init — show a button to start the card capture.
                // The record needs to be saved first (required fields filled).
                this.state.status = "idle";
            }
        });
    }

    async _initStripe() {
        this.state.status = "loading";

        // Ensure the wizard record is saved to the DB first — in a target=new
        // dialog the record is virtual (no resId) until explicitly saved.
        if (!this.props.record.resId) {
            try {
                await this.props.record.save();
            } catch (e) {
                this.state.status = "error";
                this.state.errorMessage = "Please fill in the required fields above before adding a card.";
                return;
            }
        }
        const wizardId = this.props.record.resId;
        if (!wizardId) {
            this.state.status = "error";
            this.state.errorMessage = "Please fill in the required fields above before adding a card.";
            return;
        }

        let clientSecret, publishableKey;
        try {
            const result = await rpc("/dojo/crm-convert/stripe/setup", {
                wizard_id: wizardId,
            });
            if (result.error) {
                this.state.status = "error";
                this.state.errorMessage = result.error;
                return;
            }
            clientSecret = result.client_secret;
            publishableKey = result.publishable_key;
        } catch (e) {
            this.state.status = "error";
            this.state.errorMessage = e.message || String(e) || "Network error.";
            return;
        }

        try {
            const stripeJs = await this._loadStripeJs(publishableKey);
            this.stripe = stripeJs;

            this.elements = stripeJs.elements({
                clientSecret,
                appearance: {
                    theme: "stripe",
                    variables: { colorPrimary: "#714b67" },
                },
            });

            const paymentEl = this.elements.create("payment", {
                layout: "tabs",
                wallets: { applePay: "never", googlePay: "never", link: "never" },
            });
            this._pendingPaymentEl = paymentEl;
            this.state.status = "ready";
        } catch (e) {
            this.state.status = "error";
            this.state.errorMessage = e.message || "Failed to initialise payment form.";
        }
    }

    async _loadStripeJs(publishableKey) {
        if (window.Stripe) {
            return window.Stripe(publishableKey);
        }
        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://js.stripe.com/v3/";
            script.async = true;
            script.onload = () => resolve(window.Stripe(publishableKey));
            script.onerror = () => reject(new Error("Failed to load Stripe.js"));
            document.head.appendChild(script);
        });
    }

    async onSaveCard() {
        if (!this.stripe || !this.elements) return;
        this.state.status = "processing";
        this.state.errorMessage = "";

        const { error: submitError } = await this.elements.submit();
        if (submitError) {
            this.state.errorMessage = submitError.message;
            this.state.status = "ready";
            return;
        }

        const { error, setupIntent } = await this.stripe.confirmSetup({
            elements: this.elements,
            redirect: "if_required",
        });

        if (error) {
            this.state.errorMessage = error.message;
            this.state.status = "ready";
            return;
        }

        const pmId =
            typeof setupIntent.payment_method === "string"
                ? setupIntent.payment_method
                : setupIntent.payment_method.id;

        const wizardId = this.props.record.resId;
        let result;
        try {
            result = await rpc("/dojo/crm-convert/stripe/confirm", {
                wizard_id: wizardId,
                payment_method_id: pmId,
            });
        } catch (e) {
            this.state.status = "error";
            this.state.errorMessage = e.message || String(e) || "Network error saving card.";
            return;
        }

        if (result.error) {
            this.state.status = "error";
            this.state.errorMessage = result.error;
            return;
        }

        this.state.status = "done";
        this.state.cardDisplay = result.display || "Card saved";

        await this.props.record.load();
    }

    async onRetry() {
        this.state.errorMessage = "";
        await this._initStripe();
    }

    async onSkipChange(evt) {
        await this.props.record.update({ skip_payment: evt.target.checked });
        if (evt.target.checked) {
            this.state.status = "idle";
        }
    }
}

registry.category("view_widgets").add("crm_convert_stripe_payment", {
    component: CrmConvertStripePayment,
});
