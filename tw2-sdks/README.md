# Triggerware SDKs

Triggerware SDKs are typed clients for communicating with a Triggerware server without constructing JSON-RPC requests directly. They expose Triggerware tables, queries, triggers, agents, tools, connectors, and other runtime operations through native language APIs.


## Install Triggerware

Install the Triggerware server and built-in `tw` connector using the installer for your platform.

### macOS

```sh
curl -fsSL https://tw2-releases.s3.us-east-2.amazonaws.com/install.sh | sh
curl -fsSL https://tw2-releases.s3.us-east-2.amazonaws.com/cli/install.sh | sh
```

### Windows

```powershell
irm https://tw2-releases.s3.us-east-2.amazonaws.com/install.ps1 | iex
irm https://tw2-releases.s3.us-east-2.amazonaws.com/cli/install.ps1 | iex
```

Then run:

```
triggerware start
```

By default, a locally running Triggerware server accepts TCP SDK connections at `localhost:5221`.

For more documentation, run `triggerware help`, or use the Triggerware plugin in Claude Code or Codex to ask questions.

## SDKs

Triggerware supports [Python](python/README.md) (`pip install triggerware`), [Rust](rust/README.md) (`cargo add triggerware`), and [Node.js](node/README.md) (`npm install triggerware`).

## Install the Triggerware Plugin

Install the Triggerware plugin to use Triggerware from Codex or Claude Code.

### Codex

```sh
codex plugin marketplace add triggerware/tw2-integrations
codex plugin add triggerware@triggerware
```

### Claude Code

```sh
claude plugin marketplace add triggerware/tw2-integrations
claude plugin install triggerware@triggerware
```
