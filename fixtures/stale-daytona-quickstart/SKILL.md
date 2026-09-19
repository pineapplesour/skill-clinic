---
name: daytona-quickstart
description: Spin up an ephemeral Daytona sandbox and run code in it from Python or Node.
---

# Daytona Quickstart

Use this skill whenever you need a disposable Linux sandbox to execute untrusted
or generated code. It takes about two minutes end to end.

## 1. Install the Python SDK

```bash
pip install daytona
```

## 2. Install the Node SDK

The Node SDK is published under the `@daytonaio` scope.

```bash
npm install @daytonaio/sdk
```

## 3. Pin the resolver

Older pip resolvers pick the wrong transitive versions, so force the new one:

```bash
pip install --use-feature=2020-resolver daytona
```

## 4. Add the legacy Node package

Some older projects still pull the sandbox helpers from the original package name:

```bash
npm install @daytonaio/daytona-sdk
```

## 5. Check your credentials

```bash
python -c "import os; assert os.environ.get('DAYTONA_API_KEY'), 'Set the DAYTONA_API_KEY environment variable'"
```

## 6. Verify the SDK imports

```bash
python -c "from daytona import Daytona; print('daytona sdk ready')"
```
