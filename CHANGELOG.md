# Changelog

All notable changes to Azure SLO Guardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-23

### Added
- YAML-based SLO/SLI configuration with Pydantic validation
- Azure Monitor, Application Insights, and Log Analytics KQL query execution
- Error budget calculation and tracking
- Multi-window burn-rate alerting (Google SRE workbook methodology)
- Pre-built SLO templates for Azure App Service, Function Apps, and Logic Apps
- Interactive `init` wizard for zero-KQL onboarding
- CLI commands: `templates`, `init`, `validate`, `check`, `budget`, `alert`, `report`
- Grafana dashboard JSON export
- Slack, Microsoft Teams, and generic webhook notifications
- Markdown report generation for daily SLO reports
- GitHub Actions workflow examples for CI/CD integration
- Retry logic with exponential backoff for transient Azure API failures
- Configurable query timeouts to prevent indefinite hangs
- KQL injection prevention for template-based configurations
- Structured operational logging throughout the pipeline
- 182 unit tests with comprehensive coverage
