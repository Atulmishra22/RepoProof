# Contributing to RepoProof

Thank you for your interest in contributing to RepoProof! We welcome contributions of all kinds, including bug fixes, new features, documentation updates, and design improvements.

## Code of Conduct

Please be respectful, collaborative, and inclusive in all communications and contributions.

## How to Contribute

### 1. Report Bugs & Request Features
If you find a bug or have a feature request, please open an Issue on GitHub. Describe the issue in detail, including steps to reproduce it and your system environment.

### 2. Submit Pull Requests
1. **Fork the Repository**: Create a personal copy of the repository on GitHub.
2. **Clone the Fork**: Clone your fork to your local system.
3. **Create a Feature Branch**: Use a descriptive branch name (`git checkout -b feature/amazing-feature`).
4. **Make Your Changes**: Write clean, modular, and well-documented code. Maintain style consistency with the rest of the project.
5. **Run the Verification Suites**:
   - Backend unit tests: `docker exec repoproof-backend python -m pytest`
   - Frontend E2E tests: `npx playwright test`
6. **Commit Your Changes**: Keep commits atomic and write clear, descriptive commit messages.
7. **Push to Your Fork**: Push the branch to your GitHub fork.
8. **Open a Pull Request**: Submit your PR targeting our `main` branch. Provide a detailed summary of your changes in the PR description.

## Development Setup

See the [Local Setup & Installation](README.md#⚙️-local-setup--installation) section of the README for detailed instructions on spinning up the development environment using Docker Compose and Next.js.
