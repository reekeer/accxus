# Contributing to accxus

Thank you for your interest in contributing to accxus! We welcome contributions from everyone. This project is open-source, and we appreciate help with bug fixes, new features, and improvements.

---

## How to Contribute

### 🐛 Reporting Bugs
If you find a bug, please open an issue on GitHub with a clear description of the problem and steps to reproduce it.

### ✨ Feature Requests
Have an idea for a new feature? Open an issue to discuss it with the community before starting work.

### 🔨 Pull Requests
1. Fork the repository.
2. Create a new branch for your changes (`git checkout -b feature/my-new-feature`).
3. Make your changes and ensure they follow the project's code style.
4. Add or update tests as necessary.
5. Commit your changes and push to your fork.
6. Open a Pull Request with a detailed description of your changes.

---

## Requirements

### Python Version
Code must be compatible with **Python 3.10 and above**.

### Quality Checks
Before submitting a PR, please run the following checks:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Linting
ruff check src/ tests/

# Type checking
pyright src/

# Run tests
pytest tests/
```

### Code Style
- Use **ruff** for linting.
- Use **pyright** for type checking (strict mode).
- Keep code clean and well-documented where necessary.
- Include `from __future__ import annotations` in files using type hints.

---

## License
By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
