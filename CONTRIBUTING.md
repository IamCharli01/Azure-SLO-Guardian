# Contributing to Azure SLO Guardian

Thank you for your interest in contributing to Azure SLO Guardian! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Azure subscription (for testing)
- Git

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/azure-slo-guardian.git
   cd azure-slo-guardian
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Run tests**
   ```bash
   pytest
   ```

## Development Workflow

### Code Style

We use:
- **Black** for code formatting
- **Ruff** for linting
- **MyPy** for type checking

Format and lint your code before committing:

```bash
black azure_slo_guardian tests
ruff check azure_slo_guardian tests
mypy azure_slo_guardian
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=azure_slo_guardian --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run unit tests only (no Azure credentials needed)
pytest -m unit

# Run integration tests (requires Azure credentials)
pytest -m integration
```

### Type Hints

All code should include type hints. Use `mypy` to verify:

```bash
mypy azure_slo_guardian
```

## Pull Request Process

1. **Fork the repository** and create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following our coding standards

3. **Add tests** for new functionality

4. **Update documentation** as needed

5. **Ensure all tests pass**
   ```bash
   pytest
   black azure_slo_guardian tests
   ruff check azure_slo_guardian tests
   mypy azure_slo_guardian
   ```

6. **Commit your changes** with clear, descriptive messages
   ```bash
   git commit -m "Add feature: description of what you did"
   ```

7. **Push to your fork** and create a pull request

8. **Wait for review** - maintainers will review your PR and provide feedback

## Coding Standards

### Python Style

- Follow PEP 8
- Use meaningful variable names
- Keep functions focused and small
- Add docstrings to all public functions and classes
- Use type hints

### Docstring Format

Use Google-style docstrings:

```python
def calculate_error_budget(sli: float, target: float) -> float:
    """Calculate error budget from SLI and target.

    Args:
        sli: Current service level indicator (0-100)
        target: Target SLO percentage (0-100)

    Returns:
        Remaining error budget percentage

    Raises:
        ValueError: If sli or target is out of range
    """
    if not 0 <= sli <= 100 or not 0 <= target <= 100:
        raise ValueError("SLI and target must be between 0 and 100")
    
    return target - sli
```

### Testing Guidelines

- Write tests for all new features
- Aim for high code coverage (>80%)
- Use pytest fixtures for common setup
- Mark integration tests with `@pytest.mark.integration`
- Mock Azure SDK calls in unit tests

Example test:

```python
import pytest
from azure_slo_guardian.config import Objective

class TestObjective:
    """Test Objective model."""

    def test_valid_objective(self):
        """Test creating a valid objective."""
        obj = Objective(target=99.9, window="30d")
        assert obj.target == 99.9
        assert obj.window == "30d"

    def test_invalid_target(self):
        """Test that invalid target raises error."""
        with pytest.raises(ValueError):
            Objective(target=101, window="30d")
```

## Project Structure

```
azure-slo-guardian/
├── azure_slo_guardian/       # Main package
│   ├── __init__.py
│   ├── cli.py               # CLI interface
│   ├── config.py            # Configuration models
│   ├── slo_calculator.py    # SLO calculations
│   ├── query_engine.py      # Azure query execution
│   ├── burn_rate.py         # Burn-rate alerting
│   ├── exporters/           # Export functionality
│   └── notifiers/           # Notification integrations
├── tests/                   # Test suite
├── examples/                # Example configurations
├── docs/                    # Documentation
└── pyproject.toml          # Project configuration
```

## Adding New Features

### Adding a New SLI Type

1. Add enum value to `SLIType` in `config.py`
2. Update `SLIConfig` validation
3. Add calculation logic to `SLOCalculator`
4. Add tests
5. Update documentation

### Adding a New Query Type

1. Add enum value to `QueryType` in `config.py`
2. Implement query execution in `AzureQueryEngine`
3. Add tests
4. Update documentation with examples

### Adding an Exporter

1. Create new file in `azure_slo_guardian/exporters/`
2. Implement exporter class
3. Add CLI command in `cli.py`
4. Add tests
5. Update README

## Documentation

- Update README.md for user-facing changes
- Add docstrings to all public APIs
- Include examples for new features
- Update CHANGELOG.md

## Reporting Issues

When reporting issues, please include:

- Azure SLO Guardian version
- Python version
- Operating system
- Detailed description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

## Feature Requests

Feature requests are welcome! Please:

- Check existing issues first
- Clearly describe the feature and its use case
- Explain why it would be valuable
- Consider implementation complexity

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

Open an issue or reach out to the maintainers.

Thank you for contributing to Azure SLO Guardian! 🚀
