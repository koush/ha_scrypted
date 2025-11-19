## TODO

1. Cache Scrypted resources in Home Assistant
   - Resources are currently served from Scrypted over the ingress proxy and may fail if Scrypted is remote or temporarily unavailable.
   - Cache the web-components assets locally whenever they are fetched through `ScryptedView` and expose the cached files via a registered static path, falling back to the cache on ingress failures.
   - Ensure the local static path is registered on setup and cleaned up on unload, mirroring the approach used in `lock_code_manager`.

2. Add automated testing and coverage requirements
   - Introduce a test suite with code coverage reporting (e.g., Codecov) to enforce minimum component-level and overall coverage for new PRs.
   - Once the baseline coverage is in place, gate future changes on maintaining those thresholds.

3. Generate native camera entities via the Scrypted engineio API
   - Investigate using Scrypted's engineio API to surface each managed camera as a Home Assistant entity, along with relevant events.
   - Forward Scrypted events into Home Assistant so users can leverage HA automations (in addition to or instead of Scrypted automations) without manual wiring.
   - With entities representing each device, the custom frontend cards could be configured by selecting HA entities rather than copying Scrypted device IDs manually.

4. Improve card configuration UX
   - Open an issue describing how the cards can adopt Home Assistant's graphical card configuration flow per the guidance in https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card#graphical-card-configuration.
   - The cards are simple enough that the built-in form editor should work once the schema is defined, making the setup more approachable.
