# Monero RPC Payment Module for Odoo 18

## Overview

This module provides Monero cryptocurrency payment integration for Odoo 18 using direct RPC calls to the Monero daemon and wallet. The module has been completely refactored from previous versions to ensure compatibility with Odoo 18's architecture while maintaining the core functionality of processing Monero payments.

## Key Features

- Full compatibility with Odoo 18
- RPC communication with Monero daemon/wallet using Python Monero
- Automated payment verification through scheduled jobs
- Support for multiple wallet addresses as long `payment_ids` (which were used in previous version) are no longer supported
- Seamless integration with Odoo's payment flow

## Technical Migration Details

### Odoo 18 Compatibility

This module has been specifically redesigned for Odoo 18, addressing compatibility breaks from previous versions (v15/v16/v17). Key architectural changes have been implemented to align with Odoo 18's framework requirements while maintaining the module's functionality.

### Payment Provider Implementation

The module now implements the `payment.provider` model instead of the deprecated `payment.acquirer` model that was used in versions prior to v15. This change follows Odoo's payment framework evolution and ensures proper integration with the current payment flow system.

### Secondary Address System

The module has moved away from using the long `payment_ids` (which are no longer supported) to using secondary Monero addresses for payment tracking. This architectural change provides better isolation between transactions and improves the reliability of payment matching.

### Automated Payment Verification

The module implements Odoo cron jobs to:

- Periodically check for incoming transactions
- Verify transaction confirmations
- Update payment statuses accordingly
- Reconcile completed payments with orders

This automation ensures payment integrity and reduces manual verification requirements.

## Installation Requirements

- Odoo 18
- Access to a Monero wallet RPC instance
- Proper network configuration for RPC communication

## Configuration

After installation, the module can be configured through the Odoo Payment Provider settings:

1. Enable the Monero payment provider
2. Configure Monero RPC connection details
3. Set confirmation thresholds and verification intervals
4. Test the connection to ensure proper communication

## Package reorganization

The 2 modules monero-rpc-odoo and monero-rpc-odoo-pos have been merged into one and following the naming convention for payment modules renamed to payment_monero_rpc.

## Upgrading from Previous Versions

Due to significant changes in both Odoo's payment framework and this module's architecture, a clean installation is recommended when upgrading from versions prior to Odoo 18. Data migration scripts are included but should be tested in a staging environment before use in production.

# Odoo Module Migration Compatibility Table

## Overview of Version Transitions

| Migration Path | Compatibility Level | Major Changes | Development Effort |
|----------------|---------------------|---------------|-------------------|
| 15 → 16        | Moderate           | Architecture changes, View modifications | Medium |
| 16 → 17        | Challenging        | Python requirements, Major UI/UX changes | High |
| 17 → 18        | Moderate           | API changes, New features integration | Medium |
| 15 → 17        | Difficult          | Combined challenges of both migrations | Very High |
| 16 → 18        | Difficult          | Multiple architectural changes | High |
| 15 → 18        | Very Difficult     | Comprehensive rewrite often needed | Very High |

## Detailed Migration Compatibility Table

| Component | Odoo 15 → 16 | Odoo 16 → 17 | Odoo 17 → 18 |
|-----------|-------------|-------------|-------------|
| **Python Requirements** | Python 3.7+ → 3.8+ | Python 3.8+ → 3.10+ | Python 3.10+ → 3.11+ |
| **PostgreSQL** | 12+ → 13+ | 13+ → 14+ | 14+ → 15+ |
| **Model Structure** | Minor changes | Field attribute changes | New model patterns |
| **ORM Methods** | Some deprecations | Several renamed methods | API refinements |
| **View Architecture** | QWeb changes | Major view architecture changes | New view components |
| **JavaScript Framework** | Owl 1.0 → 2.0 | Owl 2.0 → 3.0 | Component architecture improvements |
| **Report System** | Minor changes | Major reporting engine update | Enhanced PDF capabilities |
| **Security Framework** | Compatible | New security features | Enhanced access control |
| **Business Logic** | Mostly compatible | Significant changes in core modules | New business patterns |
| **Module Structure** | Compatible | Directory structure changes | Standardized patterns |

## Key Technical Changes By Version

### Odoo 15 → 16

- **ORM Changes**:
  - Deprecation of `fields.Date.context_today` in favor of new approaches
  - Changes to search domain handling
  - Enhanced recordset operations

- **View Changes**:
  - Owl 2.0 adoption requiring component rewrites
  - Changes to QWeb template inheritance
  - New kanban and list view behaviors

- **API Changes**:
  - Modified HTTP controllers architecture 
  - Changes in RPC call handling
  - New decorators for controllers

### Odoo 16 → 17

- **Major Framework Changes**:
  - Python 3.10 required with new syntax possibilities
  - Large-scale view architecture redesign
  - Component-based UI replaces many older patterns

- **Core Changes**:
  - Authentication system modifications
  - Database API changes
  - New async processing capabilities

- **Frontend**:
  - Comprehensive JavaScript framework changes
  - New theming system
  - Responsive design improvements

### Odoo 17 → 18

- **Technical Foundation**:
  - Python 3.11 optimization advantages
  - New database access patterns
  - Enhanced caching mechanisms

- **Developer Experience**:
  - New developer tools and debugging
  - Improved module testing framework
  - Better documentation and typing

- **Enterprise Features**:
  - Enhanced integration capabilities
  - New API endpoints
  - Better extensibility points

## Module Migration Strategy

| Strategy Element | Recommendation |
|------------------|----------------|
| **Assessment** | Conduct thorough code analysis before migration |
| **Database** | Test data migration separately from code updates |
| **Approach** | Consider full rewrites for 15→18 migrations |
| **Testing** | Implement automated tests before migration |
| **Timeline** | Allow 1.5-3x development time compared to original module |
| **Recommended Path** | Migrate one version at a time rather than skipping |
| **Custom Modules** | Consider rebuilding vs migrating for major version jumps |
| **Community Modules** | Check for maintained versions before custom migration |

## Common Migration Issues

1. **Database Schema Conflicts**: Fields renamed or removed between versions
2. **API Deprecations**: Methods removed without direct replacements
3. **UI Component Incompatibility**: View definitions becoming invalid
4. **Report Template Failures**: QWeb reports requiring reconstruction
5. **Security Model Changes**: Access rights and rule modifications
6. **Performance Bottlenecks**: Previously efficient code becoming slow
7. **Third-party Dependencies**: Library compatibility issues

## Best Practices for Migration

1. **Modular Approach**: Migrate core functionality first, then extensions
2. **Testing Framework**: Build comprehensive tests before migration
3. **Version Control**: Use feature branches for migration work
4. **Documentation**: Document all changes and decisions during migration
5. **Incremental Testing**: Test each component after migration
6. **User Training**: Plan for training on new interfaces after migration
7. **Parallel Running**: Consider running old and new systems in parallel initially
