# Authentication Implementation Plan for llm-dev-council

## Executive Summary

After analyzing PocketBase as a potential backend solution for the llm-dev-council project, we recommend **building a native authentication and database system locally** rather than using PocketBase as an external service. While PocketBase provides a robust backend with many features, it lacks native multi-tenancy support required for the BYOK (Bring Your Own Key) per-user configuration model.

## Key Findings

### PocketBase Limitations for This Use Case:
1. **No Native Multi-tenancy**: PocketBase is designed as a single-instance backend where all user data resides in the same SQLite database. It does not provide built-in isolation for user data/configurations.
2. **No BYOK Support**: While PocketBase supports OAuth2 and API authentication, it does not offer mechanisms for users to bring and manage their own encryption keys for API configurations.
3. **Secret Storage Limitations**: Passwords are hashed (bcrypt) but API keys and other sensitive user configurations are not encrypted at rest beyond application-level settings encryption.
4. **External Service Overhead**: Running PocketBase externally adds complexity for inter-service communication, monitoring, and deployment coordination.

### Advantages of Native Solution:
1. **True Multi-tenancy**: Complete isolation of each user's data, configurations, and API keys
2. **Custom BYOK Implementation**: Ability to implement per-user key management using host-native keystores or encrypted vaults
3. **Optimized for Specific Needs**: Tailored exactly to the llm-dev-council requirements without unnecessary complexity
4. **Reduced Dependencies**: Eliminates external service deployment and communication overhead
5. **Better Performance**: Direct database access vs HTTP API calls to external service

## Recommended Implementation

### Architecture Overview
```
llm-dev-council Application
├── Authentication Service (Native Go)
│   ├── User Management (email/password, OAuth2, API keys)
│   ├── Session/JWT Handling
│   └── Multi-tenancy Context
├── Database Layer (SQLite per-user or schema-isolated)
│   ├── User-specific databases OR
│   └── Shared database with tenant_id isolation
├── Secret Management
│   ├── User API Keys → Encrypted with user-specific keys
│   ├── Keys stored in host-native keychain/keystore OR
│   └── Application-level encryption with per-user salts
├── MCP Server Management
│   ├── Per-user MCP server instances
│   ├── Configuration isolation
│   └── Resource limits per tenant
└── API Layer
    ├── REST endpoints for user operations
    └── WebSocket/SSE for real-time updates
```

### Core Components

#### 1. User Authentication System
- **Email/Password Authentication**: Using bcrypt for password hashing
- **OAuth2 Support**: Integration with common providers (Google, GitHub, etc.)
- **API Key Authentication**: For service-to-service communication
- **Multi-Factor Authentication**: Optional TOTP-based MFA
- **Session Management**: JWT tokens with refresh token rotation

#### 2. Database Strategy
**Option A: Per-User SQLite Databases** (Recommended for maximum isolation)
- Each user gets their own `user_{id}.db` file
- Automatic database creation on user registration
- Schema migrations applied per-user database
- Complete data isolation at filesystem level

**Option B: Schema-Isolated Shared Database**
- Single SQLite database with `tenant_id` on all tables
- Row-level security via automatic `tenant_id` filtering
- Simpler backup/migration management
- Slightly less isolation than per-user databases

#### 3. Secret Management System
- **User API Keys**: Encrypted using AES-256-GCM with per-user derived keys
- **Key Derivation**: PBKDF2 from user password + per-user salt
- **Host Integration**: Optional integration with OS keychains (macOS Keychain, Windows Credential Locker, Linux Secret Service)
- **Backup Keys**: Encrypted recovery keys stored securely for account recovery

#### 4. MCP Server Management Per User
- Each user can configure and manage their own MCP servers
- Server configurations stored encrypted in user's database
- Process isolation via separate containers or sandboxed execution
- Resource limits (CPU, memory) enforceable per user
- Health monitoring and auto-restart capabilities

#### 5. API Endpoints
```
Auth:
  POST /api/register          # User registration
  POST /api/login             # Email/password login
  POST /api/login/oauth2      # OAuth2 callback
  POST /api/logout            # Session termination
  POST /api/apikey            # Generate/user API keys
  GET  /api/me                # Current user profile

Users:
  GET  /api/users/{id}/config # Get user configuration (encrypted fields masked)
  PATCH /api/users/{id}/config # Update user configuration
  GET  /api/users/{id}/mcp    # List user's MCP servers
  POST /api/users/{id}/mcp    # Create new MCP server
  DELETE /api/users/{id}/mcp/{serverId} # Delete MCP server

System:
  GET  /api/health            # Health check
  GET  /api/version           # Version info
```

### Security Considerations

#### Password Storage
- Algorithm: bcrypt with cost factor 12
- Salt: Unique per-user salt stored alongside hash
- Pepper: Optional application-wide pepper in environment variable

#### API Key Storage
- Encryption: AES-256-GCM
- Key Derivation: PBKDF2-SHA256 with per-user salt
- Nonce: Random per encryption operation
- Authentication Tag: Included for integrity verification

#### Data Encryption at Rest
- Sensitive fields (API keys, OAuth tokens, etc.) encrypted before storage
- Encryption keys derived from user credentials + application secrets
- Key rotation strategy for long-term security

### Implementation Roadmap

#### Phase 1: Core Authentication & User Management (Weeks 1-2)
- [ ] User model with email, password hash, profile data
- [ ] Registration and login endpoints
- [ ] Password hashing (bcrypt) and verification
- [ ] JWT token generation and validation
- [ ] Basic user profile management

#### Phase 2: Multi-tenancy & Database Layer (Weeks 2-3)
- [ ] Database abstraction layer (per-user or shared with tenant_id)
- [ ] User-specific database initialization
- [ ] Migration system for schema updates
- [ ] Basic CRUD operations for user data

#### Phase 3: Secret Management & Encryption (Weeks 3-4)
- [ ] Encryption utilities (AES-GCM, PBKDF2)
- [ ] Secure storage for API keys and OAuth tokens
- [ ] Integration with host-native keychains (optional)
- [ ] Key derivation and management system

#### Phase 4: MCP Server Management (Weeks 4-5)
- [ ] MCP server configuration model
- [ ] Server creation, listing, update, deletion endpoints
- [ ] Process management and isolation layer
- [ ] Health monitoring and restart policies

#### Phase 5: OAuth2 & Advanced Features (Week 5)
- [ ] OAuth2 provider integration (Google, GitHub)
- [ ] Multi-factor authentication (TOTP)
- [ ] API key generation and management
- [ ] Rate limiting and abuse prevention

#### Phase 6: Testing & Hardening (Week 6)
- [ ] Security audit and penetration testing
- [ ] Performance testing and optimization
- [ ] Backup and recovery procedures
- [ ] Documentation and user guides

### Technology Stack
- **Language**: Go 1.22+ (consistent with existing project)
- **Database**: SQLite with modernc.org/sqlite driver
- **Authentication**:
  - golang.org/x/crypto/bcrypt for password hashing
  - github.com/golang-jwt/jwt/v5 for JWT handling
  - golang.org/x/oauth2 for OAuth2 flows
- **Encryption**:
  - crypto/aes, crypto/cipher for AES-GCM
  - golang.org/x/crypto/pbkdf2 for key derivation
- **Web Framework**:
  - Existing project's HTTP router (or upgrade to chi/gin if beneficial)
- **Configuration**:
  - viper or similar for configuration management
  - Environment variables for secrets

### Deployment Considerations
- **Single Binary**: Can be built as static Go binary for easy deployment
- **Configuration**: Environment variables for database paths, encryption salts, etc.
- **Backup Strategy**:
  - Per-user database files can be backed up individually
  - Encrypted backup of encryption keys (separate from data)
- **Scaling**:
  - Vertical scaling sufficient for expected user base
  - Horizontal scaling possible with shared storage for user databases
  - Consider connection pooling for SQLite if needed

### Risk Mitigation
1. **Data Loss**:
   - Regular automated backups of user databases
   - Version-controlled schema migrations
   - Tested restore procedures

2. **Security Breaches**:
   - Principle of least privilege for database access
   - Encryption keys never stored in plaintext
   - Regular dependency updates and security scanning
   - Audit logging for sensitive operations

3. **Performance Issues**:
   - SQLite WAL mode for better concurrency
   - Proper indexing on frequently queried fields
   - Connection pooling if using shared database approach
   - Caching for non-sensitive, frequently accessed data

4. **Compatibility**:
   - Maintain API compatibility with existing frontend
   - Gradual migration path if replacing existing auth
   - Comprehensive test suite to prevent regressions

## Comparison Summary: PocketBase vs Native Solution

| Feature | PocketBase | Native Solution |
|---------|------------|-----------------
| Multi-tenancy per user | ❌ No native support | ✅ Full implementation |
| BYOK for API keys | ❌ Not supported | ✅ Custom implementation possible |
| Secret encryption at rest | ⚠️ Partial (settings only) | ✅ Full per-user encryption |
| External service dependency | ✅ Required | ❌ None (native) |
| Development complexity | ⚠️ Medium (learning curve) | ✅ Lower (familiar tech) |
| Performance | ⚠️ HTTP API overhead | ✅ Direct database access |
| Customization flexibility | ⚠️ Limited by plugin system | ✅ Full control |
| Operational overhead | ✅ External service monitoring | ❌ Simpler (single process) |

## Conclusion

While PocketBase is an impressive backend solution with many features suitable for traditional applications, it does not meet the specific multi-tenancy and BYOK requirements of the llm-dev-council project. Building a native authentication and database system provides:

1. **Exact requirement fulfillment**: True user isolation and key management
2. **Better integration**: Tighter coupling with existing Go codebase
3. **Reduced complexity**: No external service management
4. **Tailored security**: Custom encryption and key management per user
5. **Long-term maintainability**: Full control over the authentication stack

The estimated development time of 5-6 weeks is justified by the improved fit with project requirements and reduced operational complexity compared to adapting PocketBase for an unsupported use case.

## Next Steps
1. Present this plan to the llm-dev-council chairmen for review
2. Gather feedback and adjust requirements as needed
3. Begin implementation with Phase 1 (Core Authentication)
4. Regular check-ins to ensure alignment with project goals