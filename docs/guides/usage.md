---
title: "Usage"
schema_type: common
status: published
owner: core-maintainer
purpose: "Usage guide for CYO Adventure."
tags:
  - guide
  - usage
---

This guide covers common usage patterns for CYO Adventure.

## Installation

### From PyPI

```bash
pip install cyo-adventure
```

### From Source

```bash
git clone https://github.com/ByronWilliamsCPA/cyo-adventure
cd cyo_adventure
uv sync --all-extras
```

## Library Usage

### Basic Import

```python
from cyo_adventure import __version__

print(f"Version: {__version__}")
```

### Logging

```python
from cyo_adventure.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging(level="DEBUG", json_logs=False)

# Get a logger
logger = get_logger(__name__)
logger.info("Hello from CYO Adventure")
```
