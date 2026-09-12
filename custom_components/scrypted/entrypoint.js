import {
    LitElement,
    html,
    css,
} from "./lit-core.min.js";

class ExamplePanel extends LitElement {
    static get properties() {
        return {
            hass: { type: Object },
            narrow: { type: Boolean },
            panel: { type: Object },
        };
    }

    render() {
        return html`
        <div style="height: 100%; display: flex; flex-direction: column;">
            <div style="display: flex; align-items: center;">
                <ha-menu-button
                slot="navigationIcon"
                .hass=${this.hass}
                .narrow=${this.narrow}
                ></ha-menu-button>
                ${this.narrow ? html`
                    <div>Home Assistant: Scrypted</div>
                ` : ""}
            </div>
            <div style="flex: 1; position: relative;">
                <iframe
                    title="Scrypted"
                    src="/api/__DOMAIN__/__TOKEN__/entrypoint.html"
                    allow="fullscreen"
                ></iframe>
            </div>
        </div>
    `;
    }

    static get styles() {
        return css`
        :host {
            /* HA 2026.8 stopped giving custom panel elements an implicit
               height (partial-panel-resolver is now height:auto), so a
               percentage chain collapses to a 0-height iframe. Size the
               host against the viewport instead.

               The viewport includes the notch and home indicator, so the
               insets have to come off again or the bottom of the iframe
               lands underneath them. HA would do that for us, but it pads
               the panel container while this height is set here, and the
               two boxes disagree. The panel config sets handle_safe_area
               so HA leaves the padding alone and this element owns both. */
            display: block;
            box-sizing: border-box;
            height: 100vh;
            height: 100dvh;
            padding-top: var(--safe-area-inset-top, 0px);
            padding-bottom: var(--safe-area-inset-bottom, 0px);
            padding-left: var(
                --safe-area-content-inset-left,
                var(--safe-area-inset-left, 0px)
            );
            padding-right: var(
                --safe-area-content-inset-right,
                var(--safe-area-inset-right, 0px)
            );
        }
        iframe {
            border: 0;
            width: 100%;
            position: absolute;
            height: 100%;
            background-color: var(--primary-background-color);
        }
    `;
    }
}
customElements.define("ha-panel-scrypted", ExamplePanel);
