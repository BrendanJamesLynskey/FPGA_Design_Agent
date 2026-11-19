"""The navigator (brief 103): a local web front end over the agent's command line.

It reads the manifest, the run records and the committed results, shows them, and builds the CLI command a click corresponds to. It runs
no design logic. It binds to 127.0.0.1, needs the access key and a per-session token, makes no network request of its own and loads no
external font or script. ``python -m navigator`` starts it; ``navigator/README.md`` says what each page shows and where each number comes from.
"""
