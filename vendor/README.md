# Vendored Scrypted Python SDK

`scrypted_client/` contains symlinks into a sibling checkout of
https://github.com/koush/scrypted (expected at `../scrypted` relative to this
repo). This mirrors `packages/python-client` in that repo, plus the extra
`server/python` modules that `plugin_remote.py` imports transitively
(`cluster_labels`, `cluster_setup`, `plugin_console`, `plugin_pip`,
`plugin_volume`, `plugin_repl`).

`custom_components/scrypted/sdk_compat.py` adds this directory to `sys.path`
when the published SDK package is not installed. Recreate the links with:

    mkdir -p vendor/scrypted_client && cd vendor/scrypted_client
    for f in plugin_remote.py rpc.py rpc_reader.py cluster_labels.py \
             cluster_setup.py plugin_console.py plugin_pip.py \
             plugin_volume.py plugin_repl.py; do
      ln -sf ../../../scrypted/server/python/$f $f
    done
    ln -sfn ../../../scrypted/sdk/types/scrypted_python scrypted_python
