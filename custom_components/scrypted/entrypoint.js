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
