import {
    LitElement,
    html,
    css,
} from "./lit-core.min.js";

// mdi:menu. Inlined so the toggle never depends on another element being
// registered by the time this panel loads.
const MENU_ICON_PATH = "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";

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
            <div class="toolbar">
                ${this._showMenuButton ? html`
                    <button
                        class="menu"
                        aria-label="Toggle menu"
                        title="Toggle menu"
                        @click=${this._toggleMenu}
                    >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="${MENU_ICON_PATH}"></path>
                        </svg>
                    </button>
                ` : ""}
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

    get _showMenuButton() {
        /* ha-menu-button decides this from Lit context rather than from the
           properties it is given, and renders nothing when that context is
           missing. On a phone the sidebar is hidden, so losing the button
           leaves no way out of the panel short of force-quitting the app.
           Same rule, but read from what Home Assistant hands this panel. */
        return this.narrow || this.hass?.dockedSidebar === "always_hidden";
    }

    _toggleMenu() {
        /* What ha-menu-button fires. composed so it leaves this shadow root. */
        this.dispatchEvent(
            new CustomEvent("hass-toggle-menu", {
                bubbles: true,
                composed: true,
            })
        );
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
        .toolbar {
            display: flex;
            align-items: center;
        }
        .menu {
            display: flex;
            padding: 12px;
            border: 0;
            background: none;
            color: var(--primary-text-color);
            cursor: pointer;
            -webkit-tap-highlight-color: transparent;
        }
        .menu svg {
            width: 24px;
            height: 24px;
            fill: currentColor;
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
