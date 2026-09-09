# Tests

Keep all test modules and future test fixtures in this directory. Run commands
from the project root so application modules remain importable.

Run the full suite:

```sh
python3 -m unittest discover -v
```

Run a single module:

```sh
python3 -m unittest tests.test_fantasypros -v
```

The suite uses simulated provider responses and temporary storage. It makes no
external API calls and does not need the real `.env` credential. Live diagnostics
such as `fantasypros_diagnostic.py` are separate operational commands and must
not be added to automatic test discovery.
