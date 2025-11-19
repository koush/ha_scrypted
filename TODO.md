## TODO

1. Cache Scrypted resources in Home Assistant
   - Resources are currently served from Scrypted over the ingress proxy and may fail if Scrypted is remote or temporarily unavailable.
   - Cache the web-components assets locally whenever they are fetched through `ScryptedView` and expose the cached files via a registered static path, falling back to the cache on ingress failures.
   - Ensure the local static path is registered on setup and cleaned up on unload, mirroring the approach used in `lock_code_manager`.

2. Add automated testing and coverage requirements
   - Introduce a test suite with code coverage reporting (e.g., Codecov) to enforce minimum component-level and overall coverage for new PRs.
   - Once the baseline coverage is in place, gate future changes on maintaining those thresholds.
