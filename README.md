<h1 align="center">accxus</h1>

<h4 align="center">accxus is a program where you can create, manage, and modify accounts on various social networks. It uses SMS activation services for registration.</h4>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=FFFFFF" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=for-the-badge&logo=linux&logoColor=FCC624" alt="Platform">
  <img src="https://img.shields.io/badge/code%20style-black-000000?style=for-the-badge" alt="black">
  <img src="https://img.shields.io/badge/linting-ruff-orange?style=for-the-badge" alt="ruff">
  <img src="https://img.shields.io/badge/type%20checked-pyright-4B8BBE?style=for-the-badge" alt="pyright">
  <img src="https://img.shields.io/github/stars/reekeer/accxus?style=for-the-badge&logo=github&logoColor=white" alt="Stars">
  <img src="https://img.shields.io/github/last-commit/reekeer/accxus?style=for-the-badge&logo=github&logoColor=white" alt="Last Commit">
</p>

---

**accxus** is a powerful, open-source account management tool. It provides a polished terminal interface for managing social media accounts, specializing in automated registration via SMS activation services.

---

## 📦 Installation

```bash
pip install -e .
```

---

## ✨ Features

### 📱 Telegram Management
- **Sessions**: View, add, import, and manage Telegram sessions seamlessly.
- **Messages**: Bulk messaging with template support for automated outreach.
- **Parsing**: Export chat history and parse messages for data extraction.

### 🌐 Proxy Management
- **Checker**: Test proxy connectivity, latency, and anonymity.
- **Bulk Add**: Easily add multiple proxies to your configuration.
- **Management**: View and organize your proxy pool.

### ✉️ SMS Services
- **Multiple Providers**: Built-in support for SMS-Activate, HeroSMS, 5sim, and SMSPool.
- **Service Browser**: View available services and pricing from different providers.

---

## 🚀 Usage

Simply run the command:

```bash
accxus
```

Or via module:

```bash
python -m accxus
```

---

## 🗺️ Roadmap

Current status of supported social networks and platforms:

| Platform | Status |
| :--- | :---: |
| **Telegram** | ✅ Ready |
| **WhatsApp** | ⏳ Planned |
| **VK** | ⏳ Planned |
| **MAX** | ⏳ Planned |
| **FaceBook** | ⏳ Planned |
| **Instagram** | ⏳ Planned |
| **X (Twitter)** | ⏳ Planned |

---

## ⚙️ Configuration

- **Config File**: `~/.config/accxus/config.json`
- **Sessions**: `~/.local/share/accxus/sessions/`

---

## 🗂 Structure

```
accxus/
├── src/
│   └── accxus/
│       ├── core/           ← SMS and Proxy logic
│       ├── platforms/      ← Platform-specific implementations (Telegram, etc.)
│       ├── ui/             ← Rigi-based TUI implementation
│       ├── types/          ← Core data structures and models
│       └── utils/          ← Helper functions and utilities
├── tests/                  ← Unit and integration tests
├── CONTRIBUTING.md         ← Contribution guidelines
├── pyproject.toml          ← Project metadata and dependencies
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

---

## 👥 Credits

- **@IMDelewer** — Author
- **@xeltorV** — Maintainer

---

<p align="center">
  Powered by <a href="https://github.com/reekeer/Rigi">Rigi</a>
</p>

<p align="center"><sub><a href="LICENSE">MIT</a> © reekeer</sub></p>
