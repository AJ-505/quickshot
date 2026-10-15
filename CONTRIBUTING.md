# Contributing

Thanks for looking at Quickshot. Keep changes small and focused.

## Development setup

Install the system packages:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 python3-cairo wl-clipboard xdg-desktop-portal-gnome
```

Run Quickshot from the repo:

```sh
./install.sh
```

Run the tests:

```sh
./tests/run_all.sh
```

Look at the editor without the portal:

```sh
python3 tools/preview.py some.png
```

Lint:

```sh
ruff check .
```

## Code style

- Do not write code comments. The code should read from top to bottom.

## Pull requests

- One change per PR.
- Tests pass and `ruff check .` is clean.
- Include a screenshot for any UI change.
